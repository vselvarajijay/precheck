"""Build Jev calls for a check: render state per rule, merge questions, split by size.

Rules whose checks share (model, rendered state) are merged into one call with question
ids namespaced as `<rule_id>__<question_id>` (verified accepted by Jev 2026-09-26).
Calls whose estimated size exceeds Jev's limits are split into several calls; a state that
cannot fit even with a single question raises JevRequestTooLarge (never truncated).
"""

import copy
import math
from dataclasses import dataclass, field
from typing import Any

from precheck.jev.errors import JevRequestTooLarge
from precheck.jev.models import JevResponse
from precheck.schema import JevAnswer, JevCheck, JevQuestion, canonical_json
from precheck.schema.paths import parse_path, resolve

SEP = "__"
# Jev limits (docs): 64k tokens for state + all questions; 32k for state + longest question.
MAX_TOTAL_TOKENS = 64_000
MAX_STATE_PLUS_QUESTION_TOKENS = 32_000


def estimate_tokens(value: Any) -> int:
    """Conservative: ~4 chars/token on canonical JSON, plus 25% margin."""
    return math.ceil(len(canonical_json(value)) / 4 * 1.25) + 8


def render_state(data: dict[str, Any], template: list[str]) -> dict[str, Any]:
    """Only the declared paths, nested as in the request. Missing paths are omitted.

    Plain dotted paths nest (`agent.purpose` -> {"agent": {"purpose": ...}}); a path whose
    ancestor is also listed is already covered. Indexed or wildcard paths are keyed by the
    path text (`{"history[*].tool": [...]}`). Values are copied; `data` is never mutated.
    """
    out: dict[str, Any] = {}
    plain: list[list[str]] = []
    for path in template:
        segments = parse_path(path)
        if any(idx is not None for _, idx in segments):
            r = resolve(data, path)
            if not r.missing:
                out[path] = copy.deepcopy(r.value)
        else:
            plain.append([name for name, _ in segments])
    included: list[list[str]] = []
    for names in sorted(plain, key=len):
        if any(names[: len(inc)] == inc for inc in included):
            continue
        r = resolve(data, ".".join(names))
        if r.missing:
            continue
        included.append(names)
        node = out
        for name in names[:-1]:
            node = node.setdefault(name, {})
        node[names[-1]] = copy.deepcopy(r.value)
    return out


def namespaced(rule_id: str, question_id: str) -> str:
    return f"{rule_id}{SEP}{question_id}"


@dataclass
class JevCall:
    model: str
    state: dict[str, Any]
    questions: dict[str, JevQuestion] = field(default_factory=dict)
    # namespaced id -> (rule_id, question_id)
    members: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def rule_ids(self) -> list[str]:
        return sorted({rid for rid, _ in self.members.values()})


def build_calls(
    checks: list[tuple[str, JevCheck]],
    data: dict[str, Any],
    *,
    max_total: int = MAX_TOTAL_TOKENS,
    max_state_plus_question: int = MAX_STATE_PLUS_QUESTION_TOKENS,
) -> list[JevCall]:
    """`checks` is [(rule_id, JevCheck)]; `data` is `CheckRequest.as_data()`."""
    groups: dict[tuple[str, str], JevCall] = {}
    for rule_id, check in checks:
        state = render_state(data, check.state_template)
        key = (check.model, canonical_json(state))
        call = groups.setdefault(key, JevCall(model=check.model, state=state))
        for qid, q in check.questions.items():
            nid = namespaced(rule_id, qid)
            call.questions[nid] = q
            call.members[nid] = (rule_id, qid)
    calls: list[JevCall] = []
    for call in groups.values():
        calls.extend(_split(call, max_total, max_state_plus_question))
    return calls


def _split(call: JevCall, max_total: int, max_state_plus_question: int) -> list[JevCall]:
    state_tokens = estimate_tokens(call.state)
    sizes = {
        nid: estimate_tokens({nid: q.model_dump(mode="json", by_alias=True)})
        for nid, q in call.questions.items()
    }
    for nid, size in sizes.items():
        if state_tokens + size > max_state_plus_question:
            raise JevRequestTooLarge(
                f"state (~{state_tokens} tokens) + question {nid} (~{size}) exceeds "
                f"{max_state_plus_question}; narrow the rule's state_template"
            )
    if state_tokens + sum(sizes.values()) <= max_total:
        return [call]
    chunks: list[JevCall] = []
    current = JevCall(model=call.model, state=call.state)
    used = state_tokens
    for nid, q in call.questions.items():
        if current.questions and used + sizes[nid] > max_total:
            chunks.append(current)
            current = JevCall(model=call.model, state=call.state)
            used = state_tokens
        current.questions[nid] = q
        current.members[nid] = call.members[nid]
        used += sizes[nid]
    chunks.append(current)
    return chunks


def split_answers(call: JevCall, response: JevResponse) -> dict[str, dict[str, JevAnswer]]:
    """De-namespace answers: {rule_id: {question_id: answer}} (unanswered ids omitted)."""
    out: dict[str, dict[str, JevAnswer]] = {}
    for nid, answer in response.answers.items():
        if nid in call.members:
            rule_id, qid = call.members[nid]
            out.setdefault(rule_id, {})[qid] = answer
    return out
