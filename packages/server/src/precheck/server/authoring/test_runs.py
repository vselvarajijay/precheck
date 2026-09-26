"""Run golden sets and keep every answer so calibration never needs new Jev calls.

A test case attached to a rule is evaluated against that rule alone (its expected verdict
is what THIS rule should say); a policy-wide case (rule_id None) against every rule in
scope. Cases run concurrently, bounded by `concurrency`.
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from precheck.core.engine import EngineRule, JevEvaluator, evaluate
from precheck.core.schema import (
    Bands,
    Gate,
    NoulOutcome,
    RuleBody,
    ScoreOutcome,
    ScoreQuestion,
    Severity,
    Verdict,
)
from precheck.server.authoring.calibration import Point, Suggestion, calibrate, score
from precheck.server.authoring.errors import ConflictError, NotFoundError
from precheck.server.authoring.test_cases import TestCase, TestCaseService
from precheck.server.db.engine import session_scope
from precheck.server.db.models import RuleRow, RuleVersionRow, TestResultRow, TestRunRow, utcnow

JEV_USD_PER_MTOK = 0.042  # input tokens only; output is free (checked 2026-09-26)
RuleStatusScope = Literal["draft", "live"]


class TestRunRequest(BaseModel):
    __test__ = False

    scope: Literal["rule", "policy"] = "rule"
    rule_id: str | None = None
    rule_status: RuleStatusScope = "draft"


class QuestionOutcome(BaseModel):
    value: float
    band: str
    verdict: Verdict


class TestResult(BaseModel):
    __test__ = False

    test_case_id: str
    name: str
    rule_id: str | None
    expected: Verdict
    actual: Verdict | None
    passed: bool
    reason: str = ""
    error: str | None = None
    latency_ms: float = 0.0
    jev: dict[str, dict[str, QuestionOutcome]] = Field(
        default_factory=dict, description="rule -> question -> outcome"
    )


class TestRun(BaseModel):
    __test__ = False

    id: str
    scope: str
    rule_id: str | None
    rule_status: str
    jev_model: str | None
    started_at: datetime
    finished_at: datetime | None
    pass_count: int
    fail_count: int
    error_count: int
    input_tokens: int
    cost_estimate: float
    results: list[TestResult] = Field(default_factory=list)


def _engine_rule(row: RuleRow, status: RuleStatusScope) -> EngineRule | None:
    version = row.live_version if status == "live" else row.current_version
    if version is None:
        return None
    return EngineRule(
        id=row.id,
        gate=Gate(row.gate),
        body=RuleBody.model_validate(version.body_json),
        version=version.version,
        name=row.name,
    )


def _plan(session: Session, req: TestRunRequest) -> list[tuple[TestCase, list[EngineRule]]]:
    """Which rules each case runs against."""
    cases = TestCaseService(session)
    if req.scope == "rule":
        if not req.rule_id:
            raise ConflictError("scope 'rule' needs rule_id")
        row = session.get(RuleRow, req.rule_id)
        if row is None:
            raise NotFoundError(f"rule {req.rule_id!r} not found")
        rule = _engine_rule(row, req.rule_status)
        if rule is None:
            raise ConflictError(f"rule {req.rule_id!r} has no {req.rule_status} version")
        return [(c, [rule]) for c in cases.list_for_rule(req.rule_id)]
    statuses = ["live"] if req.rule_status == "live" else ["draft", "live"]
    rows = list(
        session.scalars(select(RuleRow).where(RuleRow.status.in_(statuses)).order_by(RuleRow.id))
    )
    rules = {r.id: er for r in rows if (er := _engine_rule(r, req.rule_status)) is not None}
    plan = []
    for c in cases.list_all():
        if c.rule_id is None:
            plan.append((c, list(rules.values())))
        elif c.rule_id in rules:
            plan.append((c, [rules[c.rule_id]]))
    return plan


async def run_tests(
    db: sessionmaker[Session], jev: JevEvaluator, req: TestRunRequest, *, concurrency: int = 8
) -> TestRun:
    def plan() -> list[tuple[TestCase, list[EngineRule]]]:
        with session_scope(db) as s:
            return _plan(s, req)

    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(None, plan)
    started = utcnow()
    sem = asyncio.Semaphore(concurrency)

    async def one(case: TestCase, rules: list[EngineRule]) -> tuple[TestResult, int, set[str]]:
        async with sem:
            t0 = time.perf_counter()
            try:
                d = await evaluate(rules, case.check_request, jev)
            except Exception as e:  # recorded per case; the run continues
                return (
                    TestResult(
                        test_case_id=case.id,
                        name=case.name,
                        rule_id=case.rule_id,
                        expected=case.expected_verdict,
                        actual=None,
                        passed=False,
                        error=f"{type(e).__name__}: {e}",
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    ),
                    0,
                    set(),
                )
        errors = [r.error for r in d.rule_results if r.error]
        jev_out = {
            r.rule_id: {
                qid: QuestionOutcome(value=q.value, band=q.band, verdict=q.verdict)
                for qid, q in r.jev.items()
            }
            for r in d.rule_results
            if r.jev
        }
        reason = (
            "; ".join(f"{r.rule_id}: {r.reason}" for r in d.rule_results if r.matched)
            or "no rule applied"
        )
        result = TestResult(
            test_case_id=case.id,
            name=case.name,
            rule_id=case.rule_id,
            expected=case.expected_verdict,
            actual=d.verdict,
            passed=d.verdict is case.expected_verdict,
            reason=reason,
            error="; ".join(errors) or None,
            latency_ms=d.latency_ms,
            jev=jev_out,
        )
        models = set((d.versions.jev_model or "").split(",")) - {""}
        return result, d.usage.input_tokens, models

    outcomes = await asyncio.gather(*(one(c, rules) for c, rules in items))
    results = [o[0] for o in outcomes]
    tokens = sum(o[1] for o in outcomes)
    models = set().union(*(o[2] for o in outcomes)) if outcomes else set()
    run = TestRun(
        id=str(uuid.uuid4()),
        scope=req.scope,
        rule_id=req.rule_id,
        rule_status=req.rule_status,
        jev_model=",".join(sorted(models)) or None,
        started_at=started,
        finished_at=utcnow(),
        pass_count=sum(r.passed for r in results),
        fail_count=sum(not r.passed and r.error is None for r in results),
        error_count=sum(r.error is not None for r in results),
        input_tokens=tokens,
        cost_estimate=round(tokens * JEV_USD_PER_MTOK / 1_000_000, 8),
        results=results,
    )

    def store() -> None:
        with session_scope(db) as s:
            _store(s, run, items)

    await loop.run_in_executor(None, store)
    return run


def _store(session: Session, run: TestRun, items: list[tuple[TestCase, list[EngineRule]]]) -> None:
    session.add(
        TestRunRow(
            id=run.id,
            scope=run.scope,
            rule_id=run.rule_id,
            rule_status=run.rule_status,
            jev_model=run.jev_model,
            started_at=run.started_at,
            finished_at=run.finished_at,
            pass_count=run.pass_count,
            fail_count=run.fail_count,
            error_count=run.error_count,
            input_tokens=run.input_tokens,
            cost_estimate=run.cost_estimate,
        )
    )
    session.flush()
    for (case, rules), r in zip(items, run.results, strict=True):
        version_id = None
        if len(rules) == 1 and rules[0].version is not None:
            version_id = session.scalar(
                select(RuleVersionRow.id).where(
                    RuleVersionRow.rule_id == rules[0].id,
                    RuleVersionRow.version == rules[0].version,
                )
            )
        session.add(
            TestResultRow(
                run_id=run.id,
                test_case_id=case.id,
                rule_version_id=version_id,
                actual_verdict=r.actual.value if r.actual else None,
                decision_json={"reason": r.reason, "name": r.name, "expected": r.expected.value},
                jev_answers_json={
                    rid: {q: o.model_dump() for q, o in qs.items()} for rid, qs in r.jev.items()
                },
                latency_ms=r.latency_ms,
                passed=r.passed,
                error=r.error,
            )
        )
    session.flush()


def _run_out(session: Session, row: TestRunRow, with_results: bool = True) -> TestRun:
    results: list[TestResult] = []
    if with_results:
        for res in session.scalars(
            select(TestResultRow).where(TestResultRow.run_id == row.id).order_by(TestResultRow.id)
        ):
            meta: dict[str, Any] = res.decision_json or {}
            case_rule = (
                session.scalar(
                    select(RuleVersionRow.rule_id).where(RuleVersionRow.id == res.rule_version_id)
                )
                if res.rule_version_id
                else None
            )
            results.append(
                TestResult(
                    test_case_id=res.test_case_id,
                    name=meta.get("name", ""),
                    rule_id=case_rule,
                    expected=Verdict(meta.get("expected", "allow")),
                    actual=Verdict(res.actual_verdict) if res.actual_verdict else None,
                    passed=res.passed,
                    reason=meta.get("reason", ""),
                    error=res.error,
                    latency_ms=res.latency_ms,
                    jev={
                        rid: {q: QuestionOutcome.model_validate(o) for q, o in qs.items()}
                        for rid, qs in (res.jev_answers_json or {}).items()
                    },
                )
            )
    return TestRun(
        id=row.id,
        scope=row.scope,
        rule_id=row.rule_id,
        rule_status=row.rule_status,
        jev_model=row.jev_model,
        started_at=row.started_at,
        finished_at=row.finished_at,
        pass_count=row.pass_count,
        fail_count=row.fail_count,
        error_count=row.error_count,
        input_tokens=row.input_tokens,
        cost_estimate=row.cost_estimate,
        results=results,
    )


def get_run(session: Session, run_id: str) -> TestRun:
    row = session.get(TestRunRow, run_id)
    if row is None:
        raise NotFoundError(f"test run {run_id!r} not found")
    return _run_out(session, row)


def list_runs(session: Session, rule_id: str | None = None, limit: int = 20) -> list[TestRun]:
    stmt = select(TestRunRow).order_by(TestRunRow.started_at.desc()).limit(limit)
    if rule_id is not None:
        stmt = stmt.where(TestRunRow.rule_id == rule_id)
    return [_run_out(session, r, with_results=False) for r in session.scalars(stmt)]


# --- calibration ----------------------------------------------------------------------


class QuestionCalibration(BaseModel):
    question_id: str
    type: str
    points: list[Point]
    current: Suggestion
    suggested: Suggestion
    range: tuple[float, float]


class CalibrationResult(BaseModel):
    rule_id: str
    run_id: str
    rule_version: int
    severity: Severity
    questions: list[QuestionCalibration]
    notes: list[str] = Field(default_factory=list)


def calibrate_rule(session: Session, rule_id: str, run_id: str | None = None) -> CalibrationResult:
    """Suggest bands per Jev question from a run's stored answers (latest run by default)."""
    row = session.get(RuleRow, rule_id)
    if row is None or row.current_version is None:
        raise NotFoundError(f"rule {rule_id!r} not found")
    body = RuleBody.model_validate(row.current_version.body_json)
    if body.jev is None:
        raise ConflictError(f"rule {rule_id!r} has no Jev check to calibrate")
    run_row = (
        session.get(TestRunRow, run_id)
        if run_id
        else session.scalar(
            select(TestRunRow)
            .where(TestRunRow.rule_id == rule_id)
            .order_by(TestRunRow.started_at.desc())
        )
    )
    if run_row is None:
        raise ConflictError(f"no test run for rule {rule_id!r} yet; run its tests first")
    run = _run_out(session, run_row)
    notes: list[str] = []
    questions: list[QuestionCalibration] = []
    for qid, question in body.jev.questions.items():
        outcome = body.jev.outcomes[qid]
        if not isinstance(outcome, NoulOutcome | ScoreOutcome):
            notes.append(f"{qid}: choice questions map options to verdicts; nothing to calibrate")
            continue
        points = [
            Point(value=r.jev[rule_id][qid].value, expected=r.expected)
            for r in run.results
            if rule_id in r.jev and qid in r.jev[rule_id]
        ]
        if not points:
            notes.append(f"{qid}: no stored answers in this run (cases decided without Jev)")
            continue
        top = float(len(question.criteria) - 1) if isinstance(question, ScoreQuestion) else 1.0
        step = 0.05 if isinstance(question, ScoreQuestion) else 0.01
        current = score(points, outcome.bands, body.severity)
        suggested = calibrate(points, body.severity, low=0.0, high=top, step=step)
        if suggested.cost >= current.cost:
            suggested = current  # never suggest a change that isn't strictly better
        questions.append(
            QuestionCalibration(
                question_id=qid,
                type=question.type,
                points=points,
                current=current,
                suggested=suggested,
                range=(0.0, top),
            )
        )
    return CalibrationResult(
        rule_id=rule_id,
        run_id=run_row.id,
        rule_version=row.current_version.version,
        severity=body.severity,
        questions=questions,
        notes=notes,
    )


def apply_bands(body: RuleBody, bands: dict[str, Bands]) -> RuleBody:
    """A copy of `body` with new bands for the given questions."""
    if body.jev is None:
        raise ConflictError("rule has no Jev check")
    outcomes = dict(body.jev.outcomes)
    for qid, b in bands.items():
        o = outcomes.get(qid)
        if not isinstance(o, NoulOutcome | ScoreOutcome):
            raise ConflictError(f"question {qid!r} has no bands")
        outcomes[qid] = o.model_copy(update={"bands": b})
    return body.model_copy(update={"jev": body.jev.model_copy(update={"outcomes": outcomes})})
