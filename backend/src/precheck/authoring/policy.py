"""Publishing, policy snapshots, rollback, Jev upgrade checks, and YAML import/export."""

import copy
from datetime import datetime
from typing import Any

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from precheck.authoring.dto import Provenance, RuleCreate, RuleDetail, RuleUpdate
from precheck.authoring.errors import (
    ConflictError,
    FieldProblem,
    LiveValidationError,
    NotFoundError,
)
from precheck.authoring.rules import RuleService
from precheck.authoring.test_cases import TestCaseCreate, TestCaseService
from precheck.authoring.test_runs import TestRun, TestRunRequest, run_tests
from precheck.db.engine import session_scope
from precheck.db.models import PolicyVersionRow, RuleRow
from precheck.engine import EngineRule, JevEvaluator, evaluate
from precheck.jev.errors import JevError
from precheck.schema import (
    Decision,
    Gate,
    RuleBody,
    RulePack,
    RuleSpec,
    TestCaseSpec,
    Verdict,
    content_hash,
)
from precheck.schema.jev import UNPINNED_MODELS
from precheck.schema.rule import SpecProvenance, live_problem_details

# --- policy snapshots -----------------------------------------------------------------


class PolicyRuleRef(BaseModel):
    rule_id: str
    version: int
    content_hash: str


class PolicyVersion(BaseModel):
    version: int
    rules: list[PolicyRuleRef]
    content_hash: str
    note: str | None
    created_at: datetime
    active: bool = False


def _live_refs(session: Session) -> list[PolicyRuleRef]:
    rows = session.scalars(select(RuleRow).where(RuleRow.status == "live").order_by(RuleRow.id))
    return [
        PolicyRuleRef(
            rule_id=r.id, version=r.live_version.version, content_hash=r.live_version.content_hash
        )
        for r in rows
        if r.live_version is not None
    ]


def snapshot_policy(session: Session, note: str) -> PolicyVersion:
    refs = _live_refs(session)
    latest = session.scalar(select(func.max(PolicyVersionRow.version))) or 0
    row = PolicyVersionRow(
        version=latest + 1,
        rules_json=[r.model_dump() for r in refs],
        content_hash=content_hash([r.model_dump() for r in refs]),
        note=note,
    )
    session.add(row)
    session.flush()
    return _pv_out(row, active=True)


def _pv_out(row: PolicyVersionRow, active: bool = False) -> PolicyVersion:
    return PolicyVersion(
        version=row.version,
        rules=[PolicyRuleRef.model_validate(r) for r in row.rules_json],
        content_hash=row.content_hash,
        note=row.note,
        created_at=row.created_at,
        active=active,
    )


def list_policy_versions(session: Session) -> list[PolicyVersion]:
    rows = list(session.scalars(select(PolicyVersionRow).order_by(PolicyVersionRow.version.desc())))
    return [_pv_out(r, active=i == 0) for i, r in enumerate(rows)]


def rollback(session: Session, version: int) -> PolicyVersion:
    """Re-point live rules to a snapshot (never edits versions); records a new snapshot."""
    target = session.scalar(select(PolicyVersionRow).where(PolicyVersionRow.version == version))
    if target is None:
        raise NotFoundError(f"policy version {version} not found")
    svc = RuleService(session)
    wanted = {r["rule_id"]: r["version"] for r in target.rules_json}
    for rule in session.scalars(select(RuleRow).where(RuleRow.status == "live")):
        if rule.id not in wanted:
            rule.status, rule.live_version_id = "draft", None
    for rule_id, v in wanted.items():
        target_rule = svc.repo.get(rule_id)
        version_row = svc.repo.get_version(rule_id, v)
        if target_rule is None or version_row is None:
            raise ConflictError(f"cannot roll back: {rule_id} v{v} no longer exists")
        target_rule.status, target_rule.live_version_id = "live", version_row.id
    session.flush()
    return snapshot_policy(session, note=f"rollback to v{version}")


# --- publish --------------------------------------------------------------------------


class PublishResult(BaseModel):
    rule: RuleDetail
    pinned_from: str | None = None
    pinned_to: str | None = None
    test_run: TestRun | None = None
    warnings: list[str] = Field(default_factory=list)
    policy_version: PolicyVersion


async def publish_rule(db: sessionmaker[Session], jev: JevEvaluator, rule_id: str) -> PublishResult:
    """draft -> live: pin jev-latest to the concrete model, write that as a new version, run
    the golden set on it (failures warn in the MVP), set live and snapshot the policy."""
    with session_scope(db) as s:
        detail = RuleService(s).get(rule_id)
    if detail.status == "archived":
        raise ConflictError(f"rule {rule_id!r} is archived")
    body = detail.current.body
    pinned_from = pinned_to = None
    warnings: list[str] = []
    if body.jev is not None and body.jev.model in UNPINNED_MODELS:
        try:
            pinned_to = await jev.resolve_model(body.jev.model)
        except JevError as e:
            raise ConflictError(
                f"could not resolve {body.jev.model} to a pinned version: {e}"
            ) from e
        pinned_from = body.jev.model
        body = body.model_copy(update={"jev": body.jev.model_copy(update={"model": pinned_to})})
    problems = live_problem_details(body)
    if problems:
        raise LiveValidationError([FieldProblem(field=f"body.{f}", message=m) for f, m in problems])
    if pinned_to:
        with session_scope(db) as s:
            RuleService(s).update(rule_id, RuleUpdate(body=body))
    with session_scope(db) as s:
        has_tests = bool(TestCaseService(s).list_for_rule(rule_id))
    run = None
    if has_tests:
        run = await run_tests(
            db, jev, TestRunRequest(scope="rule", rule_id=rule_id, rule_status="draft")
        )
        failing = run.fail_count + run.error_count
        if failing:
            model = pinned_to or (body.jev.model if body.jev else "this version")
            warnings.append(f"{failing} of {len(run.results)} test case(s) fail on {model}")
    else:
        warnings.append("rule has no test cases; publish without a golden set")
    with session_scope(db) as s:
        svc = RuleService(s)
        live = svc.set_status(rule_id, "live")
        pv = snapshot_policy(s, note=f"publish {rule_id} v{live.current_version}")
    return PublishResult(
        rule=live,
        pinned_from=pinned_from,
        pinned_to=pinned_to,
        test_run=run,
        warnings=warnings,
        policy_version=pv,
    )


class RuleDiff(BaseModel):
    rule_id: str
    live: Any | None
    draft: Any
    changed: bool
    live_run: TestRun | None
    draft_run: TestRun | None


# --- Jev upgrade check ----------------------------------------------------------------


class UpgradeDiff(BaseModel):
    rule_id: str
    test_case: str
    expected: Verdict
    current: Verdict
    target: Verdict
    current_values: list[float]
    target_values: list[float]


class UpgradeReport(BaseModel):
    target_model: str
    rules_checked: int
    cases_checked: int
    current_pass: int
    target_pass: int
    diffs: list[UpgradeDiff]
    jev_tokens: int


def _values(d: Decision) -> list[float]:
    return [q.value for r in d.rule_results for q in r.jev.values()]


async def upgrade_check(
    db: sessionmaker[Session], jev: JevEvaluator, target_model: str
) -> UpgradeReport:
    """Run every live Jev rule's golden set on its pinned model and on `target_model`;
    report verdict differences. Publishes nothing."""
    with session_scope(db) as s:
        rows = list(s.scalars(select(RuleRow).where(RuleRow.status == "live").order_by(RuleRow.id)))
        plan: list[tuple[EngineRule, EngineRule, list[Any]]] = []
        for row in rows:
            if row.live_version is None:
                continue
            body = RuleBody.model_validate(row.live_version.body_json)
            if body.jev is None:
                continue
            target_body = body.model_copy(
                update={"jev": body.jev.model_copy(update={"model": target_model})}
            )
            base = EngineRule(
                id=row.id, gate=Gate(row.gate), body=body, version=row.live_version.version
            )
            target = EngineRule(
                id=row.id, gate=Gate(row.gate), body=target_body, version=row.live_version.version
            )
            plan.append((base, target, TestCaseService(s).list_for_rule(row.id)))
    diffs: list[UpgradeDiff] = []
    cur_pass = tgt_pass = cases = tokens = 0
    for base, target, tcs in plan:
        for tc in tcs:
            a = await evaluate([base], tc.check_request, jev)
            b = await evaluate([target], tc.check_request, jev)
            tokens += a.usage.input_tokens + b.usage.input_tokens
            cases += 1
            cur_pass += a.verdict is tc.expected_verdict
            tgt_pass += b.verdict is tc.expected_verdict
            if a.verdict is not b.verdict:
                diffs.append(
                    UpgradeDiff(
                        rule_id=base.id,
                        test_case=tc.name,
                        expected=tc.expected_verdict,
                        current=a.verdict,
                        target=b.verdict,
                        current_values=_values(a),
                        target_values=_values(b),
                    )
                )
    return UpgradeReport(
        target_model=target_model,
        rules_checked=len(plan),
        cases_checked=cases,
        current_pass=cur_pass,
        target_pass=tgt_pass,
        diffs=diffs,
        jev_tokens=tokens,
    )


# --- YAML export / import -------------------------------------------------------------


def export_pack(session: Session) -> RulePack:
    """All live rules at their live versions, with their golden sets and provenance."""
    specs: list[RuleSpec] = []
    tests = TestCaseService(session)
    for row in session.scalars(
        select(RuleRow).where(RuleRow.status == "live").order_by(RuleRow.id)
    ):
        v = row.live_version
        if v is None:
            continue
        specs.append(
            RuleSpec(
                id=row.id,
                name=row.name,
                gate=Gate(row.gate),
                source_text=v.source_text,
                explanation=v.explanation,
                body=RuleBody.model_validate(v.body_json),
                version=v.version,
                provenance=SpecProvenance(
                    content_hash=v.content_hash,
                    jev_model=v.jev_model,
                    translator_model=v.translator_model,
                    prompt_version=v.prompt_version,
                ),
                tests=[
                    TestCaseSpec(
                        name=t.name,
                        check_request=t.check_request,
                        expected_verdict=t.expected_verdict,
                        origin=t.origin,
                    )
                    for t in tests.list_for_rule(row.id)
                ],
            )
        )
    if not specs:
        raise ConflictError("there are no live rules to export")
    return RulePack(rules=specs)


def pack_to_yaml(pack: RulePack) -> str:
    data = pack.model_dump(mode="json", by_alias=True, exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


class ImportResult(BaseModel):
    created: list[str]
    renamed: dict[str, str] = Field(default_factory=dict, description="requested id -> created id")
    tests_created: int


def import_pack(session: Session, pack: RulePack, created_by: str = "user") -> ImportResult:
    """Create every rule as a DRAFT (imports never go live); existing ids get a suffix."""
    svc = RuleService(session)
    tests = TestCaseService(session)
    created: list[str] = []
    renamed: dict[str, str] = {}
    n_tests = 0
    for spec in pack.rules:
        rule_id = spec.id if not svc.repo.exists(spec.id) else svc._unique_id(spec.id)
        prov = spec.provenance
        svc.create(
            RuleCreate(
                id=rule_id,
                name=spec.name,
                gate=spec.gate,
                body=spec.body,
                source_text=spec.source_text,
                explanation=spec.explanation,
                provenance=Provenance(
                    translator_model=prov.translator_model, prompt_version=prov.prompt_version
                )
                if prov
                else None,
            ),
            created_by=created_by,
        )
        created.append(rule_id)
        if rule_id != spec.id:
            renamed[spec.id] = rule_id
        for t in spec.tests:
            tests.create(
                TestCaseCreate(
                    rule_id=rule_id,
                    name=t.name,
                    check_request=t.check_request,
                    expected_verdict=t.expected_verdict,
                    origin=t.origin,
                )
            )
            n_tests += 1
    return ImportResult(created=created, renamed=renamed, tests_created=n_tests)


def normalized_export(pack: RulePack) -> dict[str, Any]:
    """Export content without ids-like fields (version) for round-trip comparisons."""
    data = copy.deepcopy(pack.model_dump(mode="json", by_alias=True, exclude_none=True))
    for r in data["rules"]:
        r.pop("version", None)
    return data
