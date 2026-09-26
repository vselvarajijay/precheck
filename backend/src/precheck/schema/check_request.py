"""The check request: the normalized event every rule is judged against."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from precheck.schema.common import Gate


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentInfo(_Model):
    """Who is acting."""

    id: str | None = None
    purpose: str | None = Field(default=None, description="Summary of the agent's system prompt")


class Context(_Model):
    """Why the agent is acting, if the host provides it."""

    user_goal: str | None = None
    recent_messages: list[str] | None = None


class HistoryItem(_Model):
    """A prior tool call in this session."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None


RequestKind = Literal["tool_call", "external_call", "content"]


class RequestedAction(_Model):
    """What the agent wants to do now."""

    kind: RequestKind
    tool: str | None = None
    args: dict[str, Any] | None = None
    # external_call
    method: str | None = None
    url: str | None = None
    body: str | dict[str, Any] | list[Any] | None = None
    # content (ingress / egress)
    text: str | None = None

    @model_validator(mode="after")
    def _kind_fields(self) -> Self:
        required = {"tool_call": "tool", "external_call": "url", "content": "text"}[self.kind]
        if getattr(self, required) in (None, ""):
            raise ValueError(f"request.kind={self.kind!r} requires request.{required}")
        return self


class CheckRequest(_Model):
    """Only `gate` and `request` are required; rules declare what else they need."""

    gate: Gate
    agent: AgentInfo | None = None
    context: Context | None = None
    history: list[HistoryItem] | None = None
    request: RequestedAction
    reason: str | None = Field(default=None, description="The agent's stated justification")

    def as_data(self) -> dict[str, Any]:
        """JSON form used for path resolution and Jev state (absent == null == missing)."""
        return self.model_dump(mode="json", exclude_none=True)
