"""API/MCP-facing request and response models for rules."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from precheck.core.schema import Gate, RuleBody, RuleId, RuleStatus, RuleVersion, Severity
from precheck.core.schema.common import CreatedBy


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(_In):
    translator_model: str | None = None
    prompt_version: str | None = None


class RuleCreate(_In):
    id: RuleId | None = Field(default=None, description="Slug; derived from name if omitted")
    name: str = Field(min_length=1, max_length=200)
    gate: Gate
    body: RuleBody
    source_text: str | None = None
    explanation: str | None = None
    provenance: Provenance | None = None


class RuleUpdate(_In):
    body: RuleBody
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_text: str | None = None
    explanation: str | None = None
    provenance: Provenance | None = None


class RuleStatusChange(_In):
    status: RuleStatus


class VersionSummary(BaseModel):
    version: int
    content_hash: str
    jev_model: str | None
    created_at: datetime | None
    is_current: bool
    is_live: bool


class RuleSummary(BaseModel):
    id: str
    name: str
    gate: Gate
    status: RuleStatus
    created_by: CreatedBy
    current_version: int
    live_version: int | None
    source_text: str | None
    severity: Severity
    has_deterministic: bool
    has_jev: bool
    jev_model: str | None
    requires: list[str]
    applies_to_tools: list[str] = Field(
        description="Tool names from a simple `request.tool` eq/in selector, if any"
    )
    updated_at: datetime


class RuleDetail(RuleSummary):
    current: RuleVersion
    live: RuleVersion | None
    versions: list[VersionSummary]


class RuleUpdateResult(RuleDetail):
    created_version: bool = Field(description="False when the edit was a no-op (same content)")


RuleListStatus = Literal["draft", "live", "archived", "all"]
