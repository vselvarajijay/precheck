"""Table-driven engine semantics (Jev faked; no network)."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from precheck.engine import EngineConfig, EngineRule, evaluate
from precheck.jev import JevTimeout, JevUnavailable
from precheck.schema import CheckRequest, Gate, Verdict

from .conftest import GT_500, IS_REFUND, FakeJev, det_body, jev_body, noul, req, rule


@dataclass
class Case:
    name: str
    rules: list[EngineRule]
    request: CheckRequest = field(default_factory=req)
    answers: dict[str, Any] = field(default_factory=dict)
    fail_with: Exception | None = None
    expected: Verdict = Verdict.allow
    jev_calls: int | None = None
    gate_default: bool = False
    config: EngineConfig | None = None


def choice_body(opts: dict[str, str], min_conf: float = 0.0) -> dict[str, Any]:
    return {
        "jev": {
            "state_template": ["request"],
            "questions": {
                "c": {"type": "choice", "instructions": "Kind?", "criteria": {o: o for o in opts}}
            },
            "outcomes": {"c": {"type": "choice", "map": opts, "min_confidence": min_conf}},
        }
    }


def score_body(bands: tuple[float, float], min_conf: float = 0.0) -> dict[str, Any]:
    return {
        "jev": {
            "state_template": ["request"],
            "questions": {
                "s": {
                    "type": "score",
                    "instructions": "Risk?",
                    "criteria": ["none", "low", "mid", "high", "severe"],
                }
            },
            "outcomes": {
                "s": {
                    "type": "score",
                    "min_confidence": min_conf,
                    "bands": {"escalate_at": bands[0], "deny_at": bands[1]},
                }
            },
        }
    }


def choice_ans(choice: str, conf: float) -> dict[str, Any]:
    return {"type": "choice", "choice": choice, "confidence": conf}


def score_ans(score: float, conf: float) -> dict[str, Any]:
    return {"type": "score", "score": score, "confidence": conf}


LOW_IS_BAD = jev_body() | {
    "jev": {
        **jev_body()["jev"],
        "outcomes": {
            "q": {
                "type": "noul",
                "direction": "low_is_bad",
                "bands": {"escalate_at": 0.4, "deny_at": 0.7},
            }
        },
    }
}

CASES = [
    Case(
        "no rules -> gate default allow", [], expected=Verdict.allow, gate_default=True, jev_calls=0
    ),
    Case(
        "gate mismatch -> no match",
        [rule("r", det_body(GT_500, "deny"), gate="egress")],
        request=req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 900}}),
        expected=Verdict.allow,
        gate_default=True,
    ),
    Case(
        "applies_when false -> no match",
        [rule("r", det_body(GT_500, "deny", applies_when={**IS_REFUND, "value": "other"}))],
        request=req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 900}}),
        expected=Verdict.allow,
        gate_default=True,
    ),
    Case(
        "custom gate default deny",
        [],
        expected=Verdict.deny,
        gate_default=True,
        config=EngineConfig(
            no_match={**dict.fromkeys(Gate, Verdict.allow), Gate.tool_call: Verdict.deny}
        ),
    ),
    Case(
        "requires missing -> default on_missing escalate",
        [rule("r", jev_body(requires=["context.recent_messages"]))],
        expected=Verdict.escalate,
        jev_calls=0,
    ),
    Case(
        "requires missing -> on_missing deny short-circuits",
        [rule("r", jev_body(requires=["agent.purpose"], on_missing="deny")), rule("j", jev_body())],
        request=req(agent={"id": "bot"}),
        expected=Verdict.deny,
        jev_calls=0,
    ),
    Case(
        "deterministic true -> escalate",
        [rule("r", det_body(GT_500, "escalate"))],
        request=req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 620}}),
        expected=Verdict.escalate,
    ),
    Case(
        "deterministic false, no jev -> allow",
        [rule("r", det_body(GT_500, "escalate"))],
        expected=Verdict.allow,
        gate_default=False,
    ),
    Case(
        "deterministic true allow skips its jev check",
        [
            rule(
                "r",
                det_body({"op": "eq", "path": "agent.id", "value": "bot"}, "allow") | jev_body(),
            )
        ],
        answers={"q": noul(0.99)},
        expected=Verdict.allow,
        jev_calls=0,
    ),
    Case(
        "deterministic false -> jev decides",
        [rule("r", det_body({"op": "eq", "path": "agent.id", "value": "x"}, "allow") | jev_body())],
        answers={"q": noul(0.99)},
        expected=Verdict.deny,
        jev_calls=1,
    ),
    Case(
        "noul below escalate_at -> allow",
        [rule("r", jev_body())],
        answers={"q": noul(0.39)},
        expected=Verdict.allow,
    ),
    Case(
        "noul in escalate band",
        [rule("r", jev_body())],
        answers={"q": noul(0.55)},
        expected=Verdict.escalate,
    ),
    Case(
        "noul above deny_at",
        [rule("r", jev_body())],
        answers={"q": noul(0.71)},
        expected=Verdict.deny,
    ),
    Case(
        "low_is_bad: high p allows",
        [rule("r", LOW_IS_BAD)],
        answers={"q": noul(0.9)},
        expected=Verdict.allow,
    ),
    Case(
        "low_is_bad: low p denies",
        [rule("r", LOW_IS_BAD)],
        answers={"q": noul(0.1)},
        expected=Verdict.deny,
    ),
    Case(
        "choice maps to deny",
        [rule("r", choice_body({"pii": "deny", "public": "allow"}))],
        answers={"c": choice_ans("pii", 0.95)},
        expected=Verdict.deny,
    ),
    Case(
        "choice maps to allow",
        [rule("r", choice_body({"pii": "deny", "public": "allow"}))],
        answers={"c": choice_ans("public", 0.95)},
        expected=Verdict.allow,
    ),
    Case(
        "choice low confidence -> escalate",
        [rule("r", choice_body({"pii": "deny", "public": "allow"}, min_conf=0.8))],
        answers={"c": choice_ans("public", 0.6)},
        expected=Verdict.escalate,
    ),
    Case(
        "choice unknown option -> on_error escalate",
        [rule("r", choice_body({"pii": "deny", "public": "allow"}))],
        answers={"c": choice_ans("weird", 0.9)},
        expected=Verdict.escalate,
    ),
    Case(
        "score bands deny",
        [rule("r", score_body((2, 3)))],
        answers={"s": score_ans(3.2, 0.9)},
        expected=Verdict.deny,
    ),
    Case(
        "score bands escalate",
        [rule("r", score_body((2, 3)))],
        answers={"s": score_ans(2.5, 0.9)},
        expected=Verdict.escalate,
    ),
    Case(
        "score bands allow",
        [rule("r", score_body((2, 3)))],
        answers={"s": score_ans(1.1, 0.9)},
        expected=Verdict.allow,
    ),
    Case(
        "score low confidence -> escalate",
        [rule("r", score_body((2, 3), min_conf=0.5))],
        answers={"s": score_ans(0.2, 0.3)},
        expected=Verdict.escalate,
    ),
    Case(
        "precedence deny > escalate > allow",
        [rule("a", jev_body(qid="a")), rule("b", jev_body(qid="b")), rule("c", jev_body(qid="c"))],
        answers={"a": noul(0.1), "b": noul(0.5), "c": noul(0.9)},
        expected=Verdict.deny,
        jev_calls=1,
    ),
    Case(
        "precedence escalate > allow",
        [rule("a", jev_body(qid="a")), rule("b", jev_body(qid="b"))],
        answers={"a": noul(0.1), "b": noul(0.5)},
        expected=Verdict.escalate,
    ),
    Case(
        "multi-question rule takes strictest",
        [
            rule(
                "r",
                {
                    "jev": {
                        "state_template": ["request"],
                        "questions": {
                            "x": {"type": "noul", "instructions": "X?"},
                            "y": {"type": "noul", "instructions": "Y?"},
                        },
                        "outcomes": {
                            "x": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}},
                            "y": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}},
                        },
                    }
                },
            )
        ],
        answers={"x": noul(0.1), "y": noul(0.5)},
        expected=Verdict.escalate,
    ),
    Case(
        "jev timeout, medium tool_call -> escalate",
        [rule("r", jev_body())],
        fail_with=JevTimeout("slow"),
        expected=Verdict.escalate,
    ),
    Case(
        "jev error, ingress low -> allow (flagged)",
        [rule("r", jev_body(severity="low"), gate="ingress")],
        request=req(gate="ingress", request={"kind": "content", "text": "hi"}),
        fail_with=JevUnavailable("down"),
        expected=Verdict.allow,
    ),
    Case(
        "jev error, ingress high -> escalate",
        [rule("r", jev_body(severity="high"), gate="ingress")],
        request=req(gate="ingress", request={"kind": "content", "text": "hi"}),
        fail_with=JevUnavailable("down"),
        expected=Verdict.escalate,
    ),
    Case(
        "jev error, explicit on_error deny",
        [rule("r", jev_body(on_error="deny"))],
        fail_with=JevUnavailable("down"),
        expected=Verdict.deny,
    ),
    Case(
        "jev missing answer -> on_error",
        [rule("r", jev_body())],
        answers={},
        expected=Verdict.escalate,
    ),
    Case(
        "deterministic escalate does not short-circuit jev",
        [rule("d", det_body(GT_500, "escalate")), rule("j", jev_body())],
        request=req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 620}}),
        answers={"q": noul(0.95)},
        expected=Verdict.deny,
        jev_calls=1,
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_engine_table(case: Case) -> None:
    jev = FakeJev(answers=case.answers, fail_with=case.fail_with)
    decision = await evaluate(case.rules, case.request, jev, case.config)
    assert decision.verdict is case.expected, decision.model_dump_json(indent=1)
    assert decision.gate_default_applied is case.gate_default
    if case.jev_calls is not None:
        assert len(jev.calls) == case.jev_calls


def test_table_has_enough_cases() -> None:
    assert len(CASES) >= 25


async def test_short_circuit_deterministic_deny_makes_no_jev_call() -> None:
    jev = FakeJev(answers={"q": noul(0.0)})
    rules = [
        rule("hard", det_body(GT_500, "deny")),
        rule("soft-1", jev_body()),
        rule("soft-2", jev_body(template=["reason"])),
    ]
    decision = await evaluate(
        rules,
        req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 900}}),
        jev,
    )
    assert decision.verdict is Verdict.deny
    assert len(jev.calls) == 0
    skipped = {r.rule_id: r for r in decision.rule_results}
    assert (
        skipped["soft-1"].source == "no_verdict"
        and "already denied by hard" in skipped["soft-1"].reason
    )


async def test_state_template_payload_contains_only_declared_fields() -> None:
    jev = FakeJev(answers={"q": noul(0.1)})
    await evaluate([rule("r", jev_body(template=["request.args", "agent.purpose"]))], req(), jev)
    assert jev.calls[0]["state"] == {
        "request": {"args": {"amount": 100}},
        "agent": {"purpose": "support"},
    }
    sent = str(jev.calls[0])
    for leaked in ("customer asked", "refund order 1", "lookup_order", "issue_refund"):
        assert leaked not in sent


async def test_state_template_groups_calls_by_state() -> None:
    jev = FakeJev(answers={"q": noul(0.1)})
    rules = [
        rule("a", jev_body(template=["request"])),
        rule("b", jev_body(template=["request"])),
        rule("c", jev_body(template=["reason"])),
    ]
    await evaluate(rules, req(), jev)
    assert len(jev.calls) == 2
    assert sorted(len(c["questions"]) for c in jev.calls) == [1, 2]


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.0, "allow"),
        (0.3999, "allow"),
        (0.4, "escalate"),
        (0.6999, "escalate"),
        (0.7, "deny"),
        (1.0, "deny"),
    ],
)
async def test_bands_boundary_inclusive(p: float, expected: str) -> None:
    decision = await evaluate([rule("r", jev_body())], req(), FakeJev(answers={"q": noul(p)}))
    assert decision.verdict.value == expected


async def test_bands_boundary_equal_thresholds_disable_escalate() -> None:
    for p, expected in [(0.49, "allow"), (0.5, "deny")]:
        d = await evaluate(
            [rule("r", jev_body(bands=(0.5, 0.5)))], req(), FakeJev(answers={"q": noul(p)})
        )
        assert d.verdict.value == expected


async def test_decision_contents() -> None:
    rules = [
        rule("d", det_body(GT_500, "escalate"), version=3),
        rule("j", jev_body(), version=7),
        rule("other", det_body(GT_500, "deny"), gate="egress", version=2),
    ]
    decision = await evaluate(
        rules,
        req(request={"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 620}}),
        FakeJev(answers={"q": noul(0.55)}),
    )
    by = {r.rule_id: r for r in decision.rule_results}
    assert by["d"].predicate_result is True and by["d"].predicate_inputs == {
        "request.args.amount": 620
    }
    assert by["j"].jev["q"].value == 0.55 and by["j"].jev["q"].band == "escalate ([0.4, 0.7))"
    assert not by["other"].matched
    assert decision.versions.rules == {"d": 3, "j": 7}
    assert decision.versions.jev_model == "jev-1.13.0"
    assert decision.versions.engine
    assert decision.usage.input_tokens == 100
    assert decision.latency_ms >= 0


async def test_error_is_flagged_on_rule_result() -> None:
    d = await evaluate(
        [rule("r", jev_body(), gate="ingress")],
        req(gate="ingress", request={"kind": "content", "text": "x"}),
        FakeJev(fail_with=JevUnavailable("503")),
    )
    [r] = d.rule_results
    assert r.source == "error" and r.error and "503" in r.error and r.verdict is Verdict.allow


async def test_no_jev_client_uses_on_error() -> None:
    d = await evaluate([rule("r", jev_body())], req(), None)
    assert d.verdict is Verdict.escalate and d.rule_results[0].error == "no Jev client configured"


async def test_unexpected_exception_propagates() -> None:
    with pytest.raises(RuntimeError):
        await evaluate([rule("r", jev_body())], req(), FakeJev(fail_with=RuntimeError("bug")))
