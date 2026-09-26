"""Playground: evaluate one check request, keep a run history, save test cases, examples."""

from fastapi import APIRouter, status
from starlette.concurrency import run_in_threadpool

from precheck.api.deps import JevDep, SessionFactoryDep, SettingsDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.evaluation import (
    EvaluateRequest,
    EvaluateResponse,
    PlaygroundRun,
    RuleInfo,
    list_runs,
    load_scope,
    store_run,
)
from precheck.authoring.examples import Example, PackInfo, get_pack, list_examples, list_packs
from precheck.authoring.packs import PackLoadResult, load_pack
from precheck.authoring.test_cases import TestCase, TestCaseCreate, TestCaseService
from precheck.db.engine import session_scope
from precheck.engine import EngineRule, evaluate

router = APIRouter(tags=["playground"], responses=PROBLEM_RESPONSES)


@router.post("/api/evaluate", response_model=EvaluateResponse)
async def evaluate_request(
    req: EvaluateRequest, db: SessionFactoryDep, jev: JevDep
) -> EvaluateResponse:
    """Evaluate against draft (latest versions), live (published versions) or chosen rules."""

    def load() -> tuple[list[EngineRule], list[RuleInfo]]:
        with session_scope(db) as s:
            return load_scope(s, req.scope)

    engine_rules, infos = await run_in_threadpool(load)
    decision = await evaluate(engine_rules, req.check_request, jev)

    def store() -> str:
        with session_scope(db) as s:
            return store_run(s, req.scope, req.check_request, decision)

    run_id = await run_in_threadpool(store)
    return EvaluateResponse(run_id=run_id, decision=decision, rules={r.id: r for r in infos})


@router.get("/api/playground/runs", response_model=list[PlaygroundRun])
def playground_runs(db: SessionFactoryDep, limit: int = 50) -> list[PlaygroundRun]:
    with session_scope(db) as s:
        return list_runs(s, limit=min(max(limit, 1), 200))


@router.post("/api/test-cases", response_model=TestCase, status_code=status.HTTP_201_CREATED)
def create_test_case(data: TestCaseCreate, db: SessionFactoryDep) -> TestCase:
    with session_scope(db) as s:
        return TestCaseService(s).create(data)


@router.get("/api/rules/{rule_id}/test-cases", response_model=list[TestCase])
def rule_test_cases(rule_id: str, db: SessionFactoryDep) -> list[TestCase]:
    with session_scope(db) as s:
        return TestCaseService(s).list_for_rule(rule_id)


@router.get("/api/examples", response_model=list[Example])
def examples(settings: SettingsDep) -> list[Example]:
    return list_examples(settings.examples_dir)


@router.get("/api/examples/packs", response_model=list[PackInfo])
def example_packs(settings: SettingsDep) -> list[PackInfo]:
    return list_packs(settings.examples_dir)


@router.post("/api/examples/packs/{name}/load", response_model=PackLoadResult)
def load_example_pack(name: str, settings: SettingsDep, db: SessionFactoryDep) -> PackLoadResult:
    """Create the pack's rules as drafts; rules whose ids already exist are skipped."""
    pack = get_pack(settings.examples_dir, name)
    with session_scope(db) as s:
        return load_pack(s, pack)
