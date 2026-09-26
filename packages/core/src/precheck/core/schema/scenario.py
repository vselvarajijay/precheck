"""Lab scenarios: scripted agent sessions with the expected decision for every step."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from precheck.core.schema.common import Verdict


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioAgent(_Model):
    id: str
    purpose: str


class ScenarioStep(_Model):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    expected_verdict: Verdict = Field(description="Verdict on the tool call (tool_call gate)")
    expect_reached_tool: bool = Field(description="Whether the mock tool must receive the call")
    expected_result_verdict: Verdict | None = Field(
        default=None, description="Verdict on the tool's result (ingress gate), if checked"
    )

    @model_validator(mode="after")
    def _consistent(self) -> "ScenarioStep":
        if self.expect_reached_tool != (self.expected_verdict is Verdict.allow):
            raise ValueError("expect_reached_tool must be true exactly when the call is allowed")
        if self.expected_result_verdict is not None and not self.expect_reached_tool:
            raise ValueError("a result verdict needs the call to reach the tool")
        return self


class Scenario(_Model):
    id: str
    title: str
    description: str
    agent: ScenarioAgent
    user_goal: str
    steps: list[ScenarioStep] = Field(min_length=1)
