"""Control-plane side of enforcement: serve the live policy, store decision events and
manage escalations (pending -> approved|denied -> consumed)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from precheck.authoring.errors import ConflictError, NotFoundError
from precheck.db.models import EscalationRow, LabDecisionRow, PolicyVersionRow, RuleRow, utcnow
from precheck.schema import CheckRequest, Decision, Gate, RuleBody
from precheck.schema.lab import DecisionEvent, Escalation, EscalationCreate, LivePolicy, PolicyRule


def live_policy(session: Session) -> LivePolicy:
    rows = session.scalars(select(RuleRow).where(RuleRow.status == "live").order_by(RuleRow.id))
    rules = [
        PolicyRule(
            id=r.id,
            name=r.name,
            gate=Gate(r.gate),
            version=r.live_version.version,
            body=RuleBody.model_validate(r.live_version.body_json),
        )
        for r in rows
        if r.live_version is not None
    ]
    latest = session.scalar(select(PolicyVersionRow).order_by(PolicyVersionRow.version.desc()))
    return LivePolicy(
        policy_version=latest.version if latest else None,
        content_hash=latest.content_hash if latest else None,
        rules=rules,
    )


def record_decision(session: Session, event: DecisionEvent) -> None:
    session.add(
        LabDecisionRow(
            id=event.id,
            session=event.session,
            step=event.step,
            gate=event.gate.value,
            tool=event.tool,
            verdict=event.verdict.value,
            forwarded=event.forwarded,
            escalation_id=event.escalation_id,
            check_request_json=event.check_request.model_dump(mode="json", exclude_none=True)
            if event.check_request
            else None,
            decision_json={
                "note": event.note,
                "decision": event.decision.model_dump(mode="json", by_alias=True)
                if event.decision
                else None,
            },
            latency_ms=event.latency_ms,
            created_at=event.created_at or utcnow(),
        )
    )
    session.flush()


def list_decisions(
    session: Session, session_id: str | None = None, limit: int = 200
) -> list[DecisionEvent]:
    stmt = (
        select(LabDecisionRow)
        .order_by(LabDecisionRow.created_at.desc(), LabDecisionRow.step.desc())
        .limit(limit)
    )
    if session_id:
        stmt = stmt.where(LabDecisionRow.session == session_id)
    out = []
    for r in session.scalars(stmt):
        d = r.decision_json or {}
        out.append(
            DecisionEvent(
                id=r.id,
                session=r.session,
                step=r.step,
                gate=Gate(r.gate),
                tool=r.tool,
                verdict=r.verdict,
                forwarded=r.forwarded,
                escalation_id=r.escalation_id,
                note=d.get("note"),
                check_request=CheckRequest.model_validate(r.check_request_json)
                if r.check_request_json
                else None,
                decision=Decision.model_validate(d["decision"]) if d.get("decision") else None,
                latency_ms=r.latency_ms,
                created_at=r.created_at,
            )
        )
    return out


def _escalation_out(r: EscalationRow) -> Escalation:
    return Escalation(
        id=r.id,
        session=r.session,
        tool=r.tool,
        args_hash=r.args_hash,
        status=r.status,
        check_request=CheckRequest.model_validate(r.check_request_json)
        if r.check_request_json
        else None,
        decision=Decision.model_validate(r.decision_json) if r.decision_json else None,
        created_at=r.created_at,
        resolved_at=r.resolved_at,
    )


def create_escalation(session: Session, data: EscalationCreate) -> Escalation:
    if session.get(EscalationRow, data.id) is not None:
        raise ConflictError(f"escalation {data.id!r} already exists")
    row = EscalationRow(
        id=data.id,
        session=data.session,
        tool=data.tool,
        args_hash=data.args_hash,
        status="pending",
        check_request_json=data.check_request.model_dump(mode="json", exclude_none=True)
        if data.check_request
        else None,
        decision_json=data.decision.model_dump(mode="json", by_alias=True)
        if data.decision
        else None,
    )
    session.add(row)
    session.flush()
    return _escalation_out(row)


def list_escalations(
    session: Session, status: str | None = None, ids: list[str] | None = None
) -> list[Escalation]:
    stmt = select(EscalationRow).order_by(EscalationRow.created_at.desc())
    if status:
        stmt = stmt.where(EscalationRow.status == status)
    if ids:
        stmt = stmt.where(EscalationRow.id.in_(ids))
    return [_escalation_out(r) for r in session.scalars(stmt)]


def resolve_escalation(session: Session, escalation_id: str, status: str) -> Escalation:
    row = session.get(EscalationRow, escalation_id)
    if row is None:
        raise NotFoundError(f"escalation {escalation_id!r} not found")
    allowed = {"approved": {"pending"}, "denied": {"pending"}, "consumed": {"approved"}}[status]
    if row.status not in allowed:
        raise ConflictError(
            f"escalation {escalation_id!r} is {row.status}; cannot mark it {status}"
        )
    row.status = status
    row.resolved_at = utcnow()
    session.flush()
    return _escalation_out(row)
