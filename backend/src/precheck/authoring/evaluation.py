"""Evaluate a check request against a scope of stored rules (playground, tests, lab)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from precheck.authoring.errors import NotFoundError
from precheck.db.models import PlaygroundRunRow, RuleRow, RuleVersionRow
from precheck.engine import EngineRule
from precheck.schema import CheckRequest, Decision, Gate, RuleBody, RuleSpec, RuleStatus


class EvaluateScope(BaseModel):
    """draft: every non-archived rule at its latest version (previews unpublished edits).
    live: live rules at their published version (what enforcement runs).
    rules: the listed rules at their latest version.
    inline: rules passed in the request (not stored), e.g. to try a translation before saving."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["draft", "live", "rules", "inline"] = "draft"
    rule_ids: list[str] = Field(default_factory=list)
    inline_rules: list[RuleSpec] = Field(
        default_factory=list, description="kind=inline: unsaved rules (e.g. fresh translations)"
    )

    @model_validator(mode="after")
    def _scope_inputs(self) -> "EvaluateScope":
        if self.kind == "rules" and not self.rule_ids:
            raise ValueError("scope kind 'rules' needs rule_ids")
        if self.kind == "inline" and not self.inline_rules:
            raise ValueError("scope kind 'inline' needs inline_rules")
        return self


class RuleInfo(BaseModel):
    id: str
    name: str
    status: RuleStatus
    version: int
    body: RuleBody


def load_scope(session: Session, scope: EvaluateScope) -> tuple[list[EngineRule], list[RuleInfo]]:
    if scope.kind == "inline":
        return (
            [
                EngineRule(id=r.id, gate=r.gate, body=r.body, version=0, name=r.name)
                for r in scope.inline_rules
            ],
            [
                RuleInfo(id=r.id, name=r.name, status="draft", version=0, body=r.body)
                for r in scope.inline_rules
            ],
        )
    stmt = select(RuleRow).order_by(RuleRow.created_at, RuleRow.id)
    if scope.kind == "live":
        stmt = stmt.where(RuleRow.status == "live")
    elif scope.kind == "draft":
        stmt = stmt.where(RuleRow.status != "archived")
    else:
        stmt = stmt.where(RuleRow.id.in_(scope.rule_ids))
    rows = list(session.scalars(stmt))
    if scope.kind == "rules":
        missing = sorted(set(scope.rule_ids) - {r.id for r in rows})
        if missing:
            raise NotFoundError(f"rules not found: {', '.join(missing)}")
    engine_rules: list[EngineRule] = []
    infos: list[RuleInfo] = []
    for row in rows:
        version: RuleVersionRow | None = (
            row.live_version if scope.kind == "live" else row.current_version
        )
        if version is None:
            continue
        body = RuleBody.model_validate(version.body_json)
        engine_rules.append(
            EngineRule(
                id=row.id, gate=Gate(row.gate), body=body, version=version.version, name=row.name
            )
        )
        infos.append(
            RuleInfo(
                id=row.id, name=row.name, status=row.status, version=version.version, body=body
            )
        )
    return engine_rules, infos


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_request: CheckRequest
    scope: EvaluateScope = Field(default_factory=EvaluateScope)


class EvaluateResponse(BaseModel):
    run_id: str
    decision: Decision
    rules: dict[str, RuleInfo] = Field(description="The rules evaluated, keyed by id")


class PlaygroundRun(BaseModel):
    id: str
    created_at: datetime
    scope: EvaluateScope
    check_request: CheckRequest
    decision: Decision


def store_run(
    session: Session, scope: EvaluateScope, check_request: CheckRequest, decision: Decision
) -> str:
    row = PlaygroundRunRow(
        id=str(uuid.uuid4()),
        scope_json=scope.model_dump(mode="json"),
        check_request_json=check_request.model_dump(mode="json", exclude_none=True),
        decision_json=decision.model_dump(mode="json", by_alias=True),
    )
    session.add(row)
    session.flush()
    return row.id


def list_runs(session: Session, limit: int = 50) -> list[PlaygroundRun]:
    rows = session.scalars(
        select(PlaygroundRunRow).order_by(PlaygroundRunRow.created_at.desc()).limit(limit)
    )
    return [
        PlaygroundRun(
            id=r.id,
            created_at=r.created_at,
            scope=EvaluateScope.model_validate(r.scope_json),
            check_request=CheckRequest.model_validate(r.check_request_json),
            decision=Decision.model_validate(r.decision_json),
        )
        for r in rows
    ]
