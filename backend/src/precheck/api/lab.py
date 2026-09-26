"""Endpoints data-plane adapters use (live policy, decision log, escalations) and the Lab UI
reads. Adapters call these off the request path only (background refresh / async logs)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from precheck.api.deps import SessionFactoryDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.lab import (
    create_escalation,
    get_run,
    list_decisions,
    list_escalations,
    list_runs,
    live_policy,
    record_decision,
    resolve_escalation,
    upsert_run,
    upsert_step,
)
from precheck.db.engine import session_scope
from precheck.db.models import LabDecisionRow
from precheck.schema.lab import (
    DecisionEvent,
    Escalation,
    EscalationCreate,
    LabRun,
    LivePolicy,
    RunStep,
)

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


@router.put("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def put_run(run_id: str, run: LabRun, db: SessionFactoryDep) -> None:
    """Create or update a test-agent run (and any steps it carries)."""
    with session_scope(db) as s:
        upsert_run(s, run.model_copy(update={"id": run_id}))


@router.put("/runs/{run_id}/steps/{index}", status_code=status.HTTP_204_NO_CONTENT)
def put_step(run_id: str, index: int, step: RunStep, db: SessionFactoryDep) -> None:
    with session_scope(db) as s:
        upsert_step(s, run_id, step.model_copy(update={"index": index}))


@router.get("/runs", response_model=list[LabRun])
def get_runs(
    db: SessionFactoryDep, scenario_id: str | None = None, limit: int = 50
) -> list[LabRun]:
    """Recent runs without steps (fetch one run for its steps)."""
    with session_scope(db) as s:
        return list_runs(s, scenario_id, min(max(limit, 1), 200))


@router.get("/runs/{run_id}", response_model=LabRun)
def get_lab_run(run_id: str, db: SessionFactoryDep) -> LabRun:
    with session_scope(db) as s:
        return get_run(s, run_id)
