"""Rules, versions, test cases, rule packs and decisions."""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from precheck.schema.check_request import CheckRequest
from precheck.schema.common import (
    SCHEMA_VERSION,
    CreatedBy,
    Gate,
    RuleId,
    RuleStatus,
    Severity,
    Verdict,
)
from precheck.schema.jev import JevAnswer, JevCheck, JevUsage
from precheck.schema.paths import CheckPath
from precheck.schema.predicate import Predicate


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeterministicCheck(_Model):
    """When `predicate` is true the rule's verdict is `verdict_when_true` and its Jev check
    is skipped; a deny short-circuits the whole decision. When false, the Jev check (if any)
    decides, otherwise the rule allows."""

    predicate: Predicate
    verdict_when_true: Verdict


class RuleBody(_Model):
    """The versioned, hashed part of a rule: everything that can change a verdict."""

    applies_when: Predicate | None = Field(
        default=None, description="Cheap selector; absent = applies to every request at the gate"
    )
    requires: list[CheckPath] = Field(
        default_factory=list, description="Fields that must be present, else `on_missing`"
    )
    on_missing: Verdict = Verdict.escalate
    deterministic: DeterministicCheck | None = None
    jev: JevCheck | None = None
    on_error: Verdict | None = Field(
        default=None, description="Verdict when Jev fails; absent = gate/severity default"
    )
    severity: Severity = Severity.medium

    @model_validator(mode="after")
    def _has_a_check(self) -> Self:
        if self.deterministic is None and self.jev is None:
            raise ValueError("a rule needs a deterministic check, a jev check, or both")
        return self


class TestCaseSpec(_Model):
    """A golden-set example: a check request and the verdict the rule(s) should give."""

    __test__ = False  # not a pytest class

    name: str = Field(min_length=1)
    check_request: CheckRequest
    expected_verdict: Verdict
    origin: Literal["user", "generated", "playground"] = "user"


class RuleSpec(_Model):
    """A rule as authored in YAML/JSON (rule packs, import/export)."""

    id: RuleId
    name: str = Field(min_length=1)
    gate: Gate
    source_text: str | None = None
    explanation: str | None = None
    body: RuleBody
    tests: list[TestCaseSpec] = Field(default_factory=list)


class RulePack(_Model):
    """A file of rules. `schema` is our format version; unknown versions are rejected."""

    schema_: Literal[1] = Field(alias="schema", default=1)
    rules: list[RuleSpec] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [r.id for r in self.rules]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate rule ids: {dupes}")
        return self


class RuleVersion(_Model):
    rule_id: RuleId
    version: int = Field(ge=1)
    body: RuleBody
    source_text: str | None = None
    explanation: str | None = None
    jev_model: str | None = None
    translator_model: str | None = None
    prompt_version: str | None = None
    content_hash: str
    created_at: datetime | None = None


class Rule(_Model):
    id: RuleId
    name: str
    gate: Gate
    status: RuleStatus = "draft"
    created_by: CreatedBy = "user"
    current: RuleVersion


# --- evaluation results ---------------------------------------------------------------


RuleResultSource = Literal["missing_fields", "deterministic", "jev", "error", "no_verdict"]


class QuestionResult(_Model):
    """One Jev question's answer and the verdict it mapped to."""

    answer: JevAnswer
    verdict: Verdict
    value: float = Field(description="The number compared with the bands (or the confidence)")
    band: str = Field(description="Which band/branch was hit, e.g. 'deny (>= 0.7)'")


class RuleResult(_Model):
    rule_id: str
    rule_version: int | None = None
    matched: bool
    verdict: Verdict | None = None
    source: RuleResultSource | None = None
    reason: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    predicate_result: bool | None = None
    predicate_inputs: dict[str, Any] = Field(default_factory=dict)
    jev: dict[str, QuestionResult] = Field(default_factory=dict)
    error: str | None = None


class DecisionVersions(_Model):
    engine: str
    schema_: int = Field(alias="schema", default=SCHEMA_VERSION)
    policy: str | None = None
    jev_model: str | None = None
    rules: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Decision(_Model):
    verdict: Verdict
    rule_results: list[RuleResult] = Field(default_factory=list)
    gate_default_applied: bool = False
    versions: DecisionVersions
    latency_ms: float = 0.0
    usage: JevUsage = Field(default_factory=JevUsage)


# --- live validation ------------------------------------------------------------------


def live_problems(body: RuleBody) -> list[str]:
    """Reasons this body cannot be live (empty list = publishable)."""
    try:
        data = body.model_dump(mode="json", by_alias=True)
        RuleBody.model_validate(data, context={"status": "live"})
    except ValidationError as e:
        return [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
    return []
