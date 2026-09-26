"""Quality lints on translated rules. Warnings never block; they tell a human where to look."""

import re
from dataclasses import dataclass

from pydantic import BaseModel

from precheck.schema import NoulQuestion, RuleSpec
from precheck.schema.paths import parse_path
from precheck.schema.predicate import selector_tools
from precheck.translator.draft import Requirement

# Arithmetic, numeric thresholds and literal comparisons belong in predicates (jev.md).
_NUMERIC = re.compile(
    r"\d|\$|€|£|%|\b(more|less|fewer|greater|higher|lower) than\b|\bat (least|most)\b|"
    r"\bexceed(s|ing)?\b|\bover\b|\bunder\b|\bwithin \w+ (days?|hours?|minutes?)\b|"
    r"\b(equals?|exactly|count|number of|how many)\b",
    re.IGNORECASE,
)
# Words in a question that imply which request field Jev must see.
_FIELD_HINTS: dict[str, re.Pattern[str]] = {
    "reason": re.compile(r"\breason|justif", re.IGNORECASE),
    "history": re.compile(
        r"\b(earlier|previous|prior|history|already|before this)\b", re.IGNORECASE
    ),
    "context.user_goal": re.compile(
        r"\b(user'?s? goal|user asked|customer asked|requested by the user)\b", re.IGNORECASE
    ),
    "agent.purpose": re.compile(
        r"\b(agent'?s? purpose|purpose of the agent|within (its|the agent's) role)\b", re.IGNORECASE
    ),
}


class TranslationWarning(BaseModel):
    rule_id: str | None
    code: str
    message: str


@dataclass
class ExistingRule:
    id: str
    gate: str
    tools: list[str]


def _covers(template: list[str], field: str) -> bool:
    root = parse_path(field)[0][0]
    for path in template:
        names = [n for n, _ in parse_path(path)]
        target = [n for n, _ in parse_path(field)]
        if names == target[: len(names)] or (names[0] == root and len(names) == 1):
            return True
    return False


def lint_rule(rule: RuleSpec, existing: list[ExistingRule]) -> list[TranslationWarning]:
    out: list[TranslationWarning] = []

    def warn(code: str, message: str) -> None:
        out.append(TranslationWarning(rule_id=rule.id, code=code, message=message))

    body = rule.body
    if body.jev:
        for qid, q in body.jev.questions.items():
            if _NUMERIC.search(q.instructions):
                warn(
                    "numeric_question",
                    f"Question {qid!r} looks like arithmetic or a literal comparison; "
                    "Jev is bad at these — move that part to a deterministic predicate.",
                )
            for field, pattern in _FIELD_HINTS.items():
                if pattern.search(q.instructions) and not _covers(body.jev.state_template, field):
                    warn(
                        "state_missing_field",
                        f"Question {qid!r} refers to {field} but the state template "
                        f"{body.jev.state_template} does not include it; Jev won't see it.",
                    )
            if isinstance(q, NoulQuestion):
                if q.criteria is None:
                    warn(
                        "vague_criteria",
                        f"Question {qid!r} has no true/false criteria; describe the evidence.",
                    )
                elif min(len(q.criteria.true_.split()), len(q.criteria.false_.split())) < 4:
                    warn(
                        "vague_criteria",
                        f"Question {qid!r} criteria are very short; describe observable evidence.",
                    )
    if rule.source_text and _NUMERIC.search(rule.source_text) and body.deterministic is None:
        warn(
            "numeric_without_predicate",
            "The source mentions numbers/thresholds but the rule has no deterministic check.",
        )
    if (
        body.deterministic
        and body.deterministic.verdict_when_true == "allow"
        and body.applies_when is None
        and not body.jev
    ):
        warn(
            "broad_allow",
            "Deterministic allow without a selector allows everything at this gate.",
        )
    for other in existing:
        if other.id == rule.id or other.gate != rule.gate:
            continue
        mine = set(_tools_of(rule))
        if (not mine or not other.tools) or mine & set(other.tools):
            shared = ", ".join(sorted(mine & set(other.tools))) or "all requests"
            warn(
                "possible_overlap",
                f"Overlaps existing rule {other.id!r} ({shared}); check they don't conflict.",
            )
    return out


def _tools_of(rule: RuleSpec) -> list[str]:
    return selector_tools(rule.body.applies_when)


def lint_routing(
    requirements: list[Requirement], rules: list[RuleSpec]
) -> list[TranslationWarning]:
    """Every requirement routed deterministic/judgment should be matched by a rule of that kind."""
    out: list[TranslationWarning] = []
    has_det = any(r.body.deterministic for r in rules)
    has_jev = any(r.body.jev for r in rules)
    for req in requirements:
        if req.routing in ("deterministic", "both") and not has_det:
            out.append(
                TranslationWarning(
                    rule_id=None,
                    code="routing_mismatch",
                    message=f"{req.requirement!r} was routed to code; no rule has a code check.",
                )
            )
        if req.routing in ("judgment", "both") and not has_jev:
            out.append(
                TranslationWarning(
                    rule_id=None,
                    code="routing_mismatch",
                    message=f"{req.requirement!r} was routed to Jev; no rule has a Jev check.",
                )
            )
    return out
