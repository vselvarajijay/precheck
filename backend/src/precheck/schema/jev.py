"""Jev question/answer contracts and how answers map to verdicts.

Question formats follow https://docs.typesafe.ai/api (verified 2026-09-26):
noul = yes/no probability, choice = pick one of <=255 options, score = rubric of 2-10 levels.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from precheck.schema.common import QuestionId, Verdict
from precheck.schema.paths import CheckPath

JEV_MAX_CHOICE_OPTIONS = 255
JEV_MIN_SCORE_LEVELS = 2
JEV_MAX_SCORE_LEVELS = 10

UNPINNED_MODELS = frozenset({"jev-latest", "jev-preview"})
JEV_MODEL_PATTERN = r"^jev-(latest|preview|\d+\.\d+\.\d+)$"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --- questions ------------------------------------------------------------------------


class NoulCriteria(_Model):
    true_: str = Field(alias="true", min_length=1)
    false_: str = Field(alias="false", min_length=1)


class NoulQuestion(_Model):
    type: Literal["noul"]
    instructions: str = Field(min_length=1)
    criteria: NoulCriteria | None = None


class ChoiceQuestion(_Model):
    type: Literal["choice"]
    instructions: str = Field(min_length=1)
    criteria: dict[str, str] = Field(
        description="option -> description", min_length=1, max_length=JEV_MAX_CHOICE_OPTIONS
    )

    @field_validator("criteria")
    @classmethod
    def _options_nonempty(cls, v: dict[str, str]) -> dict[str, str]:
        for opt, desc in v.items():
            if not opt.strip() or not desc.strip():
                raise ValueError("choice options and their descriptions must be non-empty")
        return v


class ScoreQuestion(_Model):
    type: Literal["score"]
    instructions: str = Field(min_length=1)
    criteria: list[str] = Field(
        description="level descriptions, level 0 first",
        min_length=JEV_MIN_SCORE_LEVELS,
        max_length=JEV_MAX_SCORE_LEVELS,
    )


JevQuestion = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


# --- outcomes: answer -> verdict --------------------------------------------------------


class Bands(_Model):
    """Thresholds, inclusive: value >= deny_at -> deny; >= escalate_at -> escalate; else allow.

    escalate_at == deny_at disables the escalate band.
    """

    escalate_at: float
    deny_at: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.escalate_at > self.deny_at:
            raise ValueError(
                f"bands: escalate_at ({self.escalate_at}) must be <= deny_at ({self.deny_at})"
            )
        return self

    def verdict(self, value: float) -> Verdict:
        if value >= self.deny_at:
            return Verdict.deny
        if value >= self.escalate_at:
            return Verdict.escalate
        return Verdict.allow


class NoulOutcome(_Model):
    """`high_is_bad`: bands apply to P(true). `low_is_bad`: bands apply to 1 - P(true)."""

    type: Literal["noul"]
    bands: Bands
    direction: Literal["high_is_bad", "low_is_bad"] = "high_is_bad"

    @field_validator("bands")
    @classmethod
    def _probability_range(cls, v: Bands) -> Bands:
        if not (0.0 <= v.escalate_at <= 1.0 and 0.0 <= v.deny_at <= 1.0):
            raise ValueError("noul bands must be within [0, 1]")
        return v


class ChoiceOutcome(_Model):
    """Each option maps to a verdict; confidence below `min_confidence` escalates."""

    type: Literal["choice"]
    map: dict[str, Verdict] = Field(min_length=1)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ScoreOutcome(_Model):
    """Bands on the expected score (a float in [0, levels-1]); low confidence escalates."""

    type: Literal["score"]
    bands: Bands
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


Outcome = Annotated[NoulOutcome | ChoiceOutcome | ScoreOutcome, Field(discriminator="type")]


# --- the Jev part of a rule -------------------------------------------------------------


class JevCheck(_Model):
    model: str = Field(
        default="jev-latest",
        pattern=JEV_MODEL_PATTERN,
        description="Pinned version (jev-X.Y.Z) required for live rules",
    )
    questions: dict[QuestionId, JevQuestion] = Field(min_length=1)
    outcomes: dict[QuestionId, Outcome]
    state_template: list[CheckPath] = Field(
        min_length=1, description="CheckRequest paths sent to Jev as state; nothing else is"
    )

    @field_validator("model")
    @classmethod
    def _pinned_when_live(cls, v: str, info: ValidationInfo) -> str:
        if (info.context or {}).get("status") == "live" and v in UNPINNED_MODELS:
            raise ValueError(f"live rules must pin a Jev version (jev-X.Y.Z), not {v!r}")
        return v

    @field_validator("state_template")
    @classmethod
    def _unique_paths(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("state_template has duplicate paths")
        return v

    @model_validator(mode="after")
    def _outcomes_match_questions(self) -> Self:
        if set(self.outcomes) != set(self.questions):
            missing = sorted(set(self.questions) - set(self.outcomes))
            extra = sorted(set(self.outcomes) - set(self.questions))
            raise ValueError(
                f"outcomes must cover exactly the questions (missing {missing}, extra {extra})"
            )
        for qid, q in self.questions.items():
            o = self.outcomes[qid]
            if o.type != q.type:
                raise ValueError(f"outcome for {qid!r} is {o.type!r} but question is {q.type!r}")
            if isinstance(q, ChoiceQuestion) and isinstance(o, ChoiceOutcome):  # noqa: SIM102
                if set(o.map) != set(q.criteria):
                    raise ValueError(
                        f"choice outcome for {qid!r} must map every option exactly: "
                        f"{sorted(q.criteria)}"
                    )
            if isinstance(q, ScoreQuestion) and isinstance(o, ScoreOutcome):
                top = len(q.criteria) - 1
                b = o.bands
                if not (0 <= b.escalate_at <= top and 0 <= b.deny_at <= top):
                    raise ValueError(f"score bands for {qid!r} must be within [0, {top}]")
        return self

    @property
    def pinned(self) -> bool:
        return self.model not in UNPINNED_MODELS


# --- answers (as returned by Jev) -------------------------------------------------------


class NoulAnswer(_Model):
    type: Literal["noul"]
    noul: float = Field(ge=0.0, le=1.0)


class ChoiceAnswer(_Model):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)


class ScoreAnswer(_Model):
    type: Literal["score"]
    score: float
    legend: dict[str, str] = Field(default_factory=dict)
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)


JevAnswer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class JevUsage(_Model):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "JevUsage") -> "JevUsage":
        return JevUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )
