"""Endpoints data-plane adapters use (live policy, decision log, escalations) and the Lab UI
reads. Adapters call these off the request path only (background refresh / async logs)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from precheck.api.deps import SessionFactoryDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.lab import (
    create_escalation,
    list_decisions,
    list_escalations,
    live_policy,
    record_decision,
    resolve_escalation,
)
from precheck.db.engine import session_scope
from precheck.db.models import LabDecisionRow
from precheck.schema.lab import DecisionEvent, Escalation, EscalationCreate, LivePolicy

router = APIRouter(prefix="/api/lab", tags=["lab"], responses=PROBLEM_RESPONSES)


@router.get("/live-policy", response_model=LivePolicy)
def get_live_policy(db: SessionFactoryDep) -> LivePolicy:
    with session_scope(db) as s:
        return live_policy(s)


@router.post("/decisions", status_code=status.HTTP_204_NO_CONTENT)
def post_decisions(events: list[DecisionEvent], db: SessionFactoryDep) -> None:
    """Batch of decision events from an adapter (idempotent per event id)."""
    with session_scope(db) as s:
        for e in events:
            if s.get(LabDecisionRow, e.id) is None:
                record_decision(s, e)


@router.get("/decisions", response_model=list[DecisionEvent])
def get_decisions(
    db: SessionFactoryDep, session: str | None = None, limit: int = 200
) -> list[DecisionEvent]:
    with session_scope(db) as s:
        return list_decisions(s, session, min(max(limit, 1), 1000))


@router.post("/escalations", response_model=Escalation, status_code=status.HTTP_201_CREATED)
def post_escalation(data: EscalationCreate, db: SessionFactoryDep) -> Escalation:
    with session_scope(db) as s:
        return create_escalation(s, data)


@router.get("/escalations", response_model=list[Escalation])
def get_escalations(
    db: SessionFactoryDep,
    status: Literal["pending", "approved", "denied", "consumed"] | None = None,
    ids: Annotated[list[str] | None, Query()] = None,
) -> list[Escalation]:
    with session_scope(db) as s:
        return list_escalations(s, status, ids)


@router.post("/escalations/{escalation_id}/{action}", response_model=Escalation)
def act_on_escalation(
    escalation_id: str, action: Literal["approve", "deny", "consume"], db: SessionFactoryDep
) -> Escalation:
    """approve/deny a pending escalation (human); consume an approved one (adapter, once)."""
    target = {"approve": "approved", "deny": "denied", "consume": "consumed"}[action]
    with session_scope(db) as s:
        return resolve_escalation(s, escalation_id, target)
