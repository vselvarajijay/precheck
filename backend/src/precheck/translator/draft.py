"""The LLM-facing translation drafts.

Claude's structured outputs need non-recursive schemas where every object is closed
(`additionalProperties: false`) and the compiled grammar stays small. So these schemas are
flat: conditions are one level (all/any + optional negate), questions and options are
lists, JSON-ish values (tool args) travel as strings, and every field is required
(nullable where it may be absent). One combined schema still exceeded the grammar limit
("compiled grammar is too large"), so the pipeline makes three calls: plan, rules, tests.
`convert.py` turns drafts into our real contracts and pydantic validates everything.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["allow", "deny", "escalate"]
GateName = Literal["tool_call", "egress", "ingress"]
Routing = Literal["deterministic", "judgment", "both"]
ConditionOp = Literal[
    "exists",
    "missing",
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "regex",
    "min_len",
    "domain_in",
    "domain_not_in",
]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirement(_Closed):
    """Step 1+2: one atomic requirement and how it must be checked."""

    source_sentence: str = Field(description="Exact sentence(s) from the business case")
    requirement: str = Field(description="One atomic, testable requirement in plain words")
    routing: Routing = Field(
        description="deterministic: numbers, dates, counts, exact matches, allowlists; "
        "judgment: needs understanding of meaning/intent; both: code guard + Jev judgment"
    )
    routing_reason: str


class Clarification(_Closed):
    id: str = Field(description="Short snake_case id")
    question: str = Field(description="A specific question the author must answer")
    options: list[str] = Field(description="2-4 concrete answer options")
    why: str = Field(description="What is ambiguous and what changes depending on the answer")


class Condition(_Closed):
    path: str = Field(
        description="CheckRequest path, e.g. request.args.amount, reason, history[*].tool"
    )
    op: ConditionOp
    value_text: str | None = Field(description="For eq/ne/regex(pattern) with text")
    value_number: float | None = Field(description="For gt/gte/lt/lte/min_len and numeric eq/ne")
    values: list[str] = Field(description="For in/not_in")
    domains: list[str] = Field(description="For domain_in/domain_not_in")


class DeterministicDraft(_Closed):
    combine: Literal["all", "any"]
    negate: bool = Field(description="True: the check matches when the conditions do NOT hold")
    conditions: list[Condition]
    verdict_when_true: Verdict


class ChoiceOption(_Closed):
    name: str = Field(description="snake_case option name")
    description: str
    verdict: Verdict


class QuestionDraft(_Closed):
    id: str = Field(description="snake_case, no double underscores")
    type: Literal["noul", "choice", "score"]
    instructions: str = Field(
        description="One judgment question; no arithmetic or literal comparisons"
    )
    criteria_true: str | None = Field(description="noul: what 'true' looks like")
    criteria_false: str | None = Field(description="noul: what 'false' looks like")
    bad_answer: Literal["true", "false"] = Field(description="noul: which answer is the violation")
    options: list[ChoiceOption] = Field(description="choice: 2-255 options")
    levels: list[str] = Field(description="score: 2-10 level descriptions, lowest first")
    escalate_at: float = Field(
        description="noul: probability of the bad answer; score: expected level"
    )
    deny_at: float
    min_confidence: float = Field(description="choice/score: escalate below this confidence")


class JevDraft(_Closed):
    state_template: list[str] = Field(description="The only request fields Jev may see")
    questions: list[QuestionDraft]


class RuleDraft(_Closed):
    id: str = Field(description="kebab-case, unique")
    name: str
    gate: GateName
    source_text: str
    explanation: str = Field(description="Plain-language restatement a human can check")
    severity: Literal["low", "medium", "high"]
    applies_to_tools: list[str] = Field(
        description="Tool names this rule applies to; empty = every request at the gate"
    )
    requires: list[str] = Field(description="Fields that must be present")
    on_missing: Verdict
    deterministic: DeterministicDraft | None
    jev: JevDraft | None
    on_error: Verdict | None


class HistoryDraft(_Closed):
    tool: str
    args_json: str = Field(description="JSON object as a string")
    result_summary: str


class TestDraft(_Closed):
    rule_id: str
    name: str
    kind: Literal["positive", "negative", "boundary", "adversarial"]
    expected_verdict: Verdict = Field(description="The verdict THIS rule should give")
    user_goal: str | None
    history: list[HistoryDraft]
    tool: str | None = Field(description="For tool_call requests")
    args_json: str = Field(description="Tool args as a JSON object string")
    url: str | None = Field(description="For external_call requests")
    text: str | None = Field(description="For content (ingress/egress) requests")
    reason: str | None


class PlanDraft(_Closed):
    """Step 1: decompose + classify, and decide whether clarification is needed."""

    status: Literal["ok", "needs_clarification"]
    requirements: list[Requirement]
    clarifications: list[Clarification]


class RulesDraft(_Closed):
    """Step 2: the rules for the planned requirements."""

    rules: list[RuleDraft]


class TestsDraft(_Closed):
    """Step 3: tests for the rules."""

    tests: list[TestDraft]
