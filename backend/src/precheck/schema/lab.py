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


# --- lab runs (test agent) --------------------------------------------------------------

RunMode = Literal["scripted", "llm"]
RunStatus = Literal["running", "passed", "failed", "completed", "error"]


class RunStep(BaseModel):
    """One tool call the test agent made through the proxy, and what happened."""

    index: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    verdict: Verdict | None = Field(
        default=None, description="Verdict on the call (tool_call gate)"
    )
    result_verdict: Verdict | None = Field(
        default=None, description="Verdict on the result (ingress)"
    )
    reached_tool: bool | None = None
    message: str = Field(default="", description="What the agent got back (truncated)")
    decisions: list[DecisionEvent] = Field(default_factory=list)
    latency_ms: float = 0.0
    # scripted runs only
    expected_verdict: Verdict | None = None
    expected_result_verdict: Verdict | None = None
    expect_reached_tool: bool | None = None
    passed: bool | None = None
    mismatches: list[str] = Field(default_factory=list)


class LabRun(BaseModel):
    id: str
    mode: RunMode
    scenario_id: str | None = None
    goal: str | None = None
    agent_id: str
    status: RunStatus
    steps: list[RunStep] = Field(default_factory=list)
    transcript: list[dict[str, Any]] = Field(default_factory=list, description="LLM mode messages")
    final_text: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
