"""Translate business cases into draft rules (the MVP core)."""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from precheck.api.deps import LLMDep, SessionFactoryDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.errors import ServiceError
from precheck.authoring.translation import (
    ClarificationAnswers,
    TranslateResponse,
    create_case,
    existing_rules,
    get_case,
    load_case_input,
    update_case,
)
from precheck.db.engine import session_scope
from precheck.translator.lints import ExistingRule
from precheck.translator.llm import LLMError
from precheck.translator.pipeline import TranslateInput, Translator

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
