from typing import Any

import pytest

from precheck.jev import JevRequestTooLarge, JevResponse, build_calls, render_state, split_answers
from precheck.schema import JevCheck, JevUsage

DATA: dict[str, Any] = {
    "gate": "tool_call",
    "agent": {"id": "bot", "purpose": "support"},
    "context": {"user_goal": "refund"},
    "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 5, "to": "card"}},
    "history": [{"tool": "lookup_order", "result_summary": "Visa"}, {"tool": "read_profile"}],
    "reason": "asked",
}


def check(
    template: list[str],
    qids: tuple[str, ...] = ("q",),
    model: str = "jev-latest",
    instructions: str = "Is it risky?",
) -> JevCheck:
    return JevCheck.model_validate(
        {
            "model": model,
            "state_template": template,
            "questions": {q: {"type": "noul", "instructions": instructions} for q in qids},
            "outcomes": {
                q: {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}} for q in qids
            },
        }
    )


def test_render_state_only_declared_fields() -> None:
    assert render_state(DATA, ["request", "reason"]) == {
        "request": DATA["request"],
        "reason": "asked",
    }
    assert render_state(DATA, ["agent.purpose", "request.args.amount"]) == {
        "agent": {"purpose": "support"},
        "request": {"args": {"amount": 5}},
    }


def test_render_state_ancestor_covers_descendant_in_any_order() -> None:
    a = render_state(DATA, ["request.args", "request"])
    b = render_state(DATA, ["request", "request.args"])
    assert a == b == {"request": DATA["request"]}


def test_render_state_wildcards_keyed_by_path_and_missing_omitted() -> None:
    out = render_state(DATA, ["history[*].tool", "context.recent_messages", "reason"])
    assert out == {"history[*].tool": ["lookup_order", "read_profile"], "reason": "asked"}


def test_render_state_does_not_mutate_input() -> None:
    import copy

    before = copy.deepcopy(DATA)
    state = render_state(DATA, ["request", "request.args.amount", "agent.purpose"])
    state["request"]["args"]["amount"] = 999
    assert before == DATA


def test_jev_batch_namespaces_and_round_trips() -> None:
    calls = build_calls(
        [("rule-a", check(["request"], ("q1", "q2"))), ("rule-b", check(["request"]))], DATA
    )
    assert len(calls) == 1
    call = calls[0]
    assert set(call.questions) == {"rule-a__q1", "rule-a__q2", "rule-b__q"}
    resp = JevResponse(
        resolved_model="jev-1.13.0",
        answers={
            nid: {"type": "noul", "noul": 0.1 * i} for i, nid in enumerate(sorted(call.questions))
        },
        usage=JevUsage(),
    )
    out = split_answers(call, resp)
    assert set(out) == {"rule-a", "rule-b"}
    assert set(out["rule-a"]) == {"q1", "q2"} and set(out["rule-b"]) == {"q"}


def test_jev_batch_two_state_templates_two_calls() -> None:
    calls = build_calls([("a", check(["request"])), ("b", check(["request", "history"]))], DATA)
    assert len(calls) == 2
    assert {tuple(c.rule_ids) for c in calls} == {("a",), ("b",)}


def test_jev_batch_same_rendered_state_merges_even_if_templates_differ() -> None:
    calls = build_calls(
        [("a", check(["request"])), ("b", check(["request.args", "request"]))], DATA
    )
    assert len(calls) == 1


def test_jev_batch_different_models_split() -> None:
    calls = build_calls(
        [("a", check(["request"])), ("b", check(["request"], model="jev-1.13.0"))], DATA
    )
    assert sorted(c.model for c in calls) == ["jev-1.13.0", "jev-latest"]


def test_jev_batch_oversize_split() -> None:
    long_q = "Is this risky? " * 40  # ~600 chars per question
    checks = [(f"r{i}", check(["reason"], instructions=long_q)) for i in range(10)]
    calls = build_calls(checks, DATA, max_total=800, max_state_plus_question=700)
    assert len(calls) > 1
    all_ids = [nid for c in calls for nid in c.questions]
    assert sorted(all_ids) == sorted(f"r{i}__q" for i in range(10))
    assert all(len(c.questions) >= 1 for c in calls)


def test_jev_batch_state_too_large_raises() -> None:
    big = {**DATA, "reason": "x" * 5000}
    with pytest.raises(JevRequestTooLarge, match="narrow the rule's state_template"):
        build_calls([("a", check(["reason"]))], big, max_total=64_000, max_state_plus_question=1000)


def test_split_answers_ignores_unknown_ids() -> None:
    call = build_calls([("a", check(["request"]))], DATA)[0]
    resp = JevResponse(
        resolved_model="m",
        usage=JevUsage(),
        answers={"a__q": {"type": "noul", "noul": 0.2}, "zz__q": {"type": "noul", "noul": 0.3}},
    )
    assert list(split_answers(call, resp)) == ["a"]
