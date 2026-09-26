"""Golden sets: test case CRUD, test runs, on-demand generation, calibration."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from precheck.api.deps import JevDep, LLMDep, SessionFactoryDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.api.translate import TranslatorUnavailable
from precheck.authoring.dto import RuleUpdate, RuleUpdateResult
from precheck.authoring.rules import RuleService
from precheck.authoring.test_cases import TestCase, TestCaseCreate, TestCaseService, TestCaseUpdate
from precheck.authoring.test_runs import (
    CalibrationResult,
    TestRun,
    TestRunRequest,
    apply_bands,
    calibrate_rule,
    get_run,
    list_runs,
    run_tests,
)
from precheck.authoring.translation import existing_rules
from precheck.db.engine import session_scope
from precheck.schema import Bands, RuleSpec
from precheck.schema.predicate import selector_tools
from precheck.translator.lints import ExistingRule
from precheck.translator.llm import LLMError
from precheck.translator.pipeline import Translator

router = APIRouter(tags=["tests"], responses=PROBLEM_RESPONSES)


@router.get("/api/test-cases", response_model=list[TestCase])
def list_test_cases(
    db: SessionFactoryDep,
    rule_id: str | None = None,
    policy: Annotated[bool, Query(description="Only policy-wide cases")] = False,
) -> list[TestCase]:
    with session_scope(db) as s:
        svc = TestCaseService(s)
        if policy:
            return svc.list_for_rule(None)
        return svc.list_for_rule(rule_id) if rule_id else svc.list_all()


@router.get("/api/test-cases/{case_id}", response_model=TestCase)
def get_test_case(case_id: str, db: SessionFactoryDep) -> TestCase:
    with session_scope(db) as s:
        return TestCaseService(s).get(case_id)


@router.put("/api/test-cases/{case_id}", response_model=TestCase)
def update_test_case(case_id: str, data: TestCaseUpdate, db: SessionFactoryDep) -> TestCase:
    with session_scope(db) as s:
        return TestCaseService(s).update(case_id, data)


@router.delete("/api/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(case_id: str, db: SessionFactoryDep) -> None:
    with session_scope(db) as s:
        TestCaseService(s).delete(case_id)


@router.post("/api/test-runs", response_model=TestRun)
async def create_test_run(req: TestRunRequest, db: SessionFactoryDep, jev: JevDep) -> TestRun:
    """Run a rule's golden set (scope=rule) or every case (scope=policy) against draft or live."""
    return await run_tests(db, jev, req)


@router.get("/api/test-runs", response_model=list[TestRun])
def test_runs(db: SessionFactoryDep, rule_id: str | None = None, limit: int = 20) -> list[TestRun]:
    """Recent runs without per-case results (fetch one run for details)."""
    with session_scope(db) as s:
        return list_runs(s, rule_id=rule_id, limit=min(max(limit, 1), 100))


@router.get("/api/test-runs/{run_id}", response_model=TestRun)
def test_run(run_id: str, db: SessionFactoryDep) -> TestRun:
    with session_scope(db) as s:
        return get_run(s, run_id)


class GenerateTestsResult(BaseModel):
    created: list[TestCase]
    errors: list[str]
    cost_usd: float


@router.post("/api/rules/{rule_id}/generate-tests", response_model=GenerateTestsResult)
async def generate_tests(rule_id: str, db: SessionFactoryDep, llm: LLMDep) -> GenerateTestsResult:
    """Ask the translator for more test cases for this rule (saved, origin=generated)."""

    def load() -> tuple[RuleSpec, list[str]]:
        with session_scope(db) as s:
            rule = RuleService(s).get(rule_id)
            spec = RuleSpec(
                id=rule.id,
                name=rule.name,
                gate=rule.gate,
                source_text=rule.current.source_text,
                explanation=rule.current.explanation,
                body=rule.current.body,
            )
            return spec, selector_tools(rule.current.body.applies_when)

    spec, tools = await run_in_threadpool(load)
    existing = await run_in_threadpool(lambda: _existing(db))
    try:
        generated = await Translator(llm, existing=existing).generate_tests(spec, tools)
    except LLMError as e:
        raise TranslatorUnavailable(str(e)) from e

    def save() -> list[TestCase]:
        with session_scope(db) as s:
            svc = TestCaseService(s)
            return [
                svc.create(
                    TestCaseCreate(
                        rule_id=rule_id,
                        name=t.test.name,
                        check_request=t.test.check_request,
                        expected_verdict=t.test.expected_verdict,
                        origin="generated",
                    )
                )
                for t in generated.tests
            ]

    created = await run_in_threadpool(save)
    return GenerateTestsResult(
        created=created, errors=generated.errors, cost_usd=generated.cost_usd
    )


def _existing(db: SessionFactoryDep) -> list[ExistingRule]:
    with session_scope(db) as s:
        return existing_rules(s)


@router.post("/api/rules/{rule_id}/calibrate", response_model=CalibrationResult)
def calibrate(rule_id: str, db: SessionFactoryDep, run_id: str | None = None) -> CalibrationResult:
    """Suggest bands from a run's stored answers (latest run by default). Never applies them
    and never calls Jev."""
    with session_scope(db) as s:
        return calibrate_rule(s, rule_id, run_id)


class ApplyBands(BaseModel):
    bands: dict[str, Bands]


@router.post("/api/rules/{rule_id}/apply-bands", response_model=RuleUpdateResult)
def apply_bands_to_draft(rule_id: str, data: ApplyBands, db: SessionFactoryDep) -> RuleUpdateResult:
    """Write suggested bands as a new draft version of the rule."""
    with session_scope(db) as s:
        svc = RuleService(s)
        body = apply_bands(svc.get(rule_id).current.body, data.bands)
        return svc.update(rule_id, RuleUpdate(body=body))
