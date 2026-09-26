"""Publish, diff, policy versions (rollback), Jev upgrade check, YAML export/import."""

import yaml
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from precheck.core.schema import RulePack
from precheck.server.api.deps import JevDep, SessionFactoryDep
from precheck.server.api.problems import PROBLEM_RESPONSES
from precheck.server.authoring.errors import FieldProblem, LiveValidationError, ServiceError
from precheck.server.authoring.policy import (
    ImportResult,
    PolicyVersion,
    PublishResult,
    RuleDiff,
    UpgradeReport,
    export_pack,
    import_pack,
    list_policy_versions,
    pack_to_yaml,
    publish_rule,
    rollback,
    upgrade_check,
)
from precheck.server.authoring.rules import RuleService
from precheck.server.authoring.test_runs import TestRun, get_run
from precheck.server.db.engine import session_scope
from precheck.server.db.models import TestRunRow

router = APIRouter(tags=["policy"], responses=PROBLEM_RESPONSES)


@router.post("/api/rules/{rule_id}/publish", response_model=PublishResult)
async def publish(rule_id: str, db: SessionFactoryDep, jev: JevDep) -> PublishResult:
    """Pin jev-latest to the concrete version, run the golden set on it (failures warn), set
    live and snapshot the policy."""
    return await publish_rule(db, jev, rule_id)


@router.get("/api/rules/{rule_id}/diff", response_model=RuleDiff)
def diff(rule_id: str, db: SessionFactoryDep) -> RuleDiff:
    """Live vs current (draft) version, with the latest test run for each."""
    with session_scope(db) as s:
        rule = RuleService(s).get(rule_id)

        def last_run(status: str) -> TestRun | None:
            row = s.scalar(
                select(TestRunRow)
                .where(TestRunRow.rule_id == rule_id, TestRunRow.rule_status == status)
                .order_by(TestRunRow.started_at.desc())
            )
            return get_run(s, row.id) if row else None

        return RuleDiff(
            rule_id=rule_id,
            live=rule.live,
            draft=rule.current,
            changed=rule.live is None or rule.live.content_hash != rule.current.content_hash,
            live_run=last_run("live"),
            draft_run=last_run("draft"),
        )


@router.get("/api/policy-versions", response_model=list[PolicyVersion])
def policy_versions(db: SessionFactoryDep) -> list[PolicyVersion]:
    """Newest first; the first is active."""
    with session_scope(db) as s:
        return list_policy_versions(s)


@router.post("/api/policy-versions/{version}/activate", response_model=PolicyVersion)
def activate(version: int, db: SessionFactoryDep) -> PolicyVersion:
    """Roll back (or forward): make exactly that snapshot's rule versions live."""
    with session_scope(db) as s:
        return rollback(s, version)


class UpgradeCheckRequest(BaseModel):
    target_model: str = Field(pattern=r"^jev-(latest|preview|\d+\.\d+\.\d+)$")


@router.post("/api/jev/upgrade-check", response_model=UpgradeReport)
async def jev_upgrade_check(
    req: UpgradeCheckRequest, db: SessionFactoryDep, jev: JevDep
) -> UpgradeReport:
    """Compare live rules' golden sets on their pinned Jev model vs `target_model`."""
    return await upgrade_check(db, jev, req.target_model)


@router.get(
    "/api/export",
    response_class=PlainTextResponse,
    responses={200: {"content": {"application/yaml": {}}, "description": "RulePack YAML"}},
)
def export(db: SessionFactoryDep) -> PlainTextResponse:
    """All live rules (live versions, golden sets, provenance) as a RulePack YAML file."""
    with session_scope(db) as s:
        text = pack_to_yaml(export_pack(s))
    return PlainTextResponse(
        text,
        media_type="application/yaml",
        headers={"content-disposition": 'attachment; filename="policy.yaml"'},
    )


class ImportRequest(BaseModel):
    yaml: str = Field(min_length=1, description="A RulePack YAML (or JSON) document")


class ImportInvalid(ServiceError):
    status = 422
    title = "Invalid rule pack"


@router.post("/api/import", response_model=ImportResult, status_code=201)
def import_rules(req: ImportRequest, db: SessionFactoryDep) -> ImportResult:
    """Validate a RulePack and create its rules as drafts (never live) with their tests."""
    try:
        data = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise ImportInvalid(f"not valid YAML: {e}") from e
    try:
        pack = RulePack.model_validate(data)
    except ValidationError as e:
        raise LiveValidationError(
            [
                FieldProblem(field=".".join(str(p) for p in err["loc"]), message=err["msg"])
                for err in e.errors()
            ]
        ) from e
    with session_scope(db) as s:
        return import_pack(s, pack)
