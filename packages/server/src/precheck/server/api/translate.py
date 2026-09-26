"""Translate business cases into draft rules (the MVP core)."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from precheck.core.schema import RuleSpec
from precheck.server.api.deps import LLMDep, SessionFactoryDep
from precheck.server.api.problems import PROBLEM_RESPONSES
from precheck.server.authoring.errors import ServiceError
from precheck.server.authoring.translation import (
    ClarificationAnswers,
    SaveResult,
    SaveTranslation,
    TranslateResponse,
    create_case,
    existing_rules,
    get_case,
    load_case_input,
    save_translation,
    update_case,
)
from precheck.server.db.engine import session_scope
from precheck.translator.lints import ExistingRule
from precheck.translator.llm import LLMError
from precheck.translator.pipeline import RefineResult, TranslateInput, Translator

router = APIRouter(prefix="/api/translate", tags=["translate"], responses=PROBLEM_RESPONSES)


class TranslatorUnavailable(ServiceError):
    status = 503
    title = "Translator unavailable"


def _existing(db: SessionFactoryDep) -> list[ExistingRule]:
    with session_scope(db) as s:
        return existing_rules(s)


@router.post("", response_model=TranslateResponse)
async def translate(inp: TranslateInput, db: SessionFactoryDep, llm: LLMDep) -> TranslateResponse:
    """Business case -> draft rules + clarifications + generated tests (nothing is saved as a
    rule yet; the business case and result are stored)."""
    existing = await run_in_threadpool(_existing, db)
    try:
        result = await Translator(llm, existing=existing).translate(inp)
    except LLMError as e:
        raise TranslatorUnavailable(str(e)) from e

    def store() -> str:
        with session_scope(db) as s:
            return create_case(s, inp, result, created_by="user")

    case_id = await run_in_threadpool(store)
    return TranslateResponse(business_case_id=case_id, result=result)


@router.post("/{case_id}/answers", response_model=TranslateResponse)
async def answer_clarifications(
    case_id: str, body: ClarificationAnswers, db: SessionFactoryDep, llm: LLMDep
) -> TranslateResponse:
    """Re-run the translation with the author's answers to the clarification questions."""

    def load() -> TranslateInput:
        with session_scope(db) as s:
            return load_case_input(s, case_id)

    inp = await run_in_threadpool(load)
    inp = inp.model_copy(update={"answers": {**inp.answers, **body.answers}})
    existing = await run_in_threadpool(_existing, db)
    try:
        result = await Translator(llm, existing=existing).translate(inp)
    except LLMError as e:
        raise TranslatorUnavailable(str(e)) from e

    def store() -> None:
        with session_scope(db) as s:
            update_case(s, case_id, inp, result)

    await run_in_threadpool(store)
    return TranslateResponse(business_case_id=case_id, result=result)


@router.get("/{case_id}", response_model=TranslateResponse)
def get_translation(case_id: str, db: SessionFactoryDep) -> TranslateResponse:
    with session_scope(db) as s:
        return get_case(s, case_id)


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/x-ndjson": {}}, "description": "NDJSON events"}},
)
async def translate_stream(
    inp: TranslateInput, db: SessionFactoryDep, llm: LLMDep
) -> StreamingResponse:
    """Same as POST /api/translate, streamed as NDJSON lines:
    {"type":"progress","stage":"plan|rules|validating|repairing|tests"} ...
    then {"type":"result","data":TranslateResponse}
    or {"type":"error","status":...,"detail":...}."""
    existing = await run_in_threadpool(_existing, db)
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def progress(stage: str) -> None:
        await queue.put({"type": "progress", "stage": stage})

    async def run() -> None:
        try:
            result = await Translator(llm, existing=existing, progress=progress).translate(inp)

            def store() -> str:
                with session_scope(db) as s:
                    return create_case(s, inp, result, created_by="user")

            case_id = await run_in_threadpool(store)
            payload = TranslateResponse(business_case_id=case_id, result=result)
            await queue.put(
                {"type": "result", "data": payload.model_dump(mode="json", by_alias=True)}
            )
        except LLMError as e:
            await queue.put({"type": "error", "status": 503, "detail": str(e)})
        finally:
            await queue.put(None)

    async def lines() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event) + "\n"
        finally:
            await task

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.post("/{case_id}/save", response_model=SaveResult, status_code=201)
def save(case_id: str, data: SaveTranslation, db: SessionFactoryDep) -> SaveResult:
    """Save the (possibly edited) translated rules as drafts, plus their generated tests."""
    with session_scope(db) as s:
        return save_translation(s, case_id, data)


class RefineRequest(BaseModel):
    rule: RuleSpec
    instruction: str = Field(min_length=1, max_length=2000)


@router.post("/refine", response_model=RefineResult)
async def refine(req: RefineRequest, db: SessionFactoryDep, llm: LLMDep) -> RefineResult:
    """Ask the translator to change one rule ("make this stricter for amounts under $50")."""
    existing = await run_in_threadpool(_existing, db)
    try:
        return await Translator(llm, existing=existing).refine(req.rule, req.instruction)
    except LLMError as e:
        raise TranslatorUnavailable(str(e)) from e
