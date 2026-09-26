"""Wire models for POST /v1/systemone."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from precheck.core.schema import JevAnswer, JevQuestion, JevUsage


class JevRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    state: Any
    questions: dict[str, JevQuestion] = Field(min_length=1)

    def wire(self) -> dict[str, Any]:
        """The exact JSON body sent to Jev (also the fixture key)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class JevResponse(BaseModel):
    """Parsed response. `resolved_model` is the concrete version Jev used (pin this)."""

    resolved_model: str
    answers: dict[str, JevAnswer]
    usage: JevUsage
    latency_ms: float = 0.0
    request_id: str | None = None
    from_fixture: bool = False
