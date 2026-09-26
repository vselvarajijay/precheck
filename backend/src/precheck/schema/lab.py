"""Contracts between the control plane (API) and data-plane adapters (e.g. the MCP proxy):
the live policy bundle they load, and the decision/escalation events they report."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from precheck.schema.check_request import CheckRequest
from precheck.schema.common import Gate, Verdict
from precheck.schema.rule import Decision, RuleBody


class PolicyRule(BaseModel):
    id: str
    name: str
    gate: Gate
    version: int
    body: RuleBody


class LivePolicy(BaseModel):
    """What enforcement runs: live rules at their published versions."""

    policy_version: int | None = Field(description="Active policy snapshot, if any")
    content_hash: str | None = None
    rules: list[PolicyRule]


class DecisionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session: str
    step: int
    gate: Gate
    tool: str | None = None
    verdict: Verdict
    forwarded: bool = Field(description="Whether the call/result was passed on")
    escalation_id: str | None = None
    note: str | None = Field(
        default=None, description="e.g. 'escalation grant used', 'no policy loaded'"
    )
    check_request: CheckRequest | None = Field(default=None, description="Omitted when redacted")
    decision: Decision | None = None
    latency_ms: float = 0.0
    created_at: datetime | None = None


EscalationStatus = Literal["pending", "approved", "denied", "consumed"]


class EscalationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session: str
    tool: str
    args_hash: str
    check_request: CheckRequest | None = None
    decision: Decision | None = None


class Escalation(EscalationCreate):
    status: EscalationStatus
    created_at: datetime | None = None
    resolved_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
