"""Small shared types: verdicts, gates, severities and identifier formats."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import StringConstraints

SCHEMA_VERSION = 1


class Verdict(StrEnum):
    allow = "allow"
    deny = "deny"
    escalate = "escalate"


# Precedence when combining rule verdicts: deny > escalate > allow.
VERDICT_RANK: dict[Verdict, int] = {Verdict.allow: 0, Verdict.escalate: 1, Verdict.deny: 2}


def strictest(verdicts: "list[Verdict] | tuple[Verdict, ...]") -> Verdict | None:
    """The winning verdict under deny > escalate > allow (None for an empty input)."""
    return max(verdicts, key=VERDICT_RANK.__getitem__, default=None)


class Gate(StrEnum):
    tool_call = "tool_call"
    egress = "egress"
    ingress = "ingress"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


RuleStatus = Literal["draft", "live", "archived"]
CreatedBy = Literal["user", "agent"]

# Rule ids are kebab-case slugs. Question ids are snake_case and never contain "__",
# because Jev batching namespaces them as "<rule_id>__<question_id>".
RuleId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")]
QuestionId = Annotated[str, StringConstraints(pattern=r"^[a-z](?:_?[a-z0-9]){0,63}$")]
