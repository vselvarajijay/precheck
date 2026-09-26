"""Rules CRUD. Thin: every call goes through RuleService."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from precheck.api.deps import SessionFactoryDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.dto import (
    RuleCreate,
    RuleDetail,
    RuleListStatus,
    RuleStatusChange,
    RuleSummary,
    RuleUpdate,
    RuleUpdateResult,
)
from precheck.authoring.policy import snapshot_policy
from precheck.authoring.rules import RuleService
from precheck.db.engine import session_scope
from precheck.schema import Gate, RuleVersion

router = APIRouter(prefix="/api/rules", tags=["rules"], responses=PROBLEM_RESPONSES)


@router.get("", response_model=list[RuleSummary])
def list_rules(
    db: SessionFactoryDep,
    gate: Gate | None = None,
    status: Annotated[RuleListStatus | None, Query(description="Default hides archived")] = None,
    q: str | None = None,
) -> list[RuleSummary]:
    with session_scope(db) as s:
        return RuleService(s).list_rules(gate=gate, status=status, q=q)


@router.post("", response_model=RuleDetail, status_code=status.HTTP_201_CREATED)
def create_rule(data: RuleCreate, db: SessionFactoryDep) -> RuleDetail:
    with session_scope(db) as s:
        return RuleService(s).create(data)


@router.get("/{rule_id}", response_model=RuleDetail)
def get_rule(rule_id: str, db: SessionFactoryDep) -> RuleDetail:
    with session_scope(db) as s:
        return RuleService(s).get(rule_id)


@router.put("/{rule_id}", response_model=RuleUpdateResult)
def update_rule(rule_id: str, data: RuleUpdate, db: SessionFactoryDep) -> RuleUpdateResult:
    """Creates a new version unless the content is unchanged (`created_version: false`)."""
    with session_scope(db) as s:
        return RuleService(s).update(rule_id, data)


@router.get("/{rule_id}/versions/{version}", response_model=RuleVersion)
def get_rule_version(rule_id: str, version: int, db: SessionFactoryDep) -> RuleVersion:
    with session_scope(db) as s:
        return RuleService(s).get_version(rule_id, version)


@router.post("/{rule_id}/status", response_model=RuleDetail)
def set_rule_status(rule_id: str, data: RuleStatusChange, db: SessionFactoryDep) -> RuleDetail:
    """`live` validates and pins the current version (a Jev version must be pinned)."""
    with session_scope(db) as s:
        svc = RuleService(s)
        was_live = svc.get(rule_id).status == "live"
        rule = svc.set_status(rule_id, data.status)
        if was_live or rule.status == "live":
            snapshot_policy(s, note=f"{rule_id} -> {rule.status} (v{rule.current_version})")
        return rule


@router.delete("/{rule_id}", response_model=RuleDetail)
def archive_rule(rule_id: str, db: SessionFactoryDep) -> RuleDetail:
    """Soft delete: sets status to archived."""
    with session_scope(db) as s:
        svc = RuleService(s)
        was_live = svc.get(rule_id).status == "live"
        rule = svc.archive(rule_id)
        if was_live:
            snapshot_policy(s, note=f"{rule_id} archived")
        return rule
