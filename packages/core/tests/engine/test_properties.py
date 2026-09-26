"""Verdict precedence is order-independent (`pytest -k precedence_property`)."""

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from precheck.core.engine import evaluate
from precheck.core.schema import Verdict, strictest

from .conftest import FakeJev, jev_body, noul, req, rule

verdicts = st.lists(st.sampled_from(list(Verdict)), min_size=1, max_size=8)


@given(verdicts, st.randoms())
def test_precedence_property_strictest_is_order_independent(vs: list[Verdict], rnd) -> None:
    shuffled = vs[:]
    rnd.shuffle(shuffled)
    assert strictest(vs) == strictest(shuffled)
    expected = (
        Verdict.deny
        if Verdict.deny in vs
        else Verdict.escalate
        if Verdict.escalate in vs
        else Verdict.allow
    )
    assert strictest(vs) is expected


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=1), min_size=1, max_size=6), st.randoms())
def test_precedence_property_engine_rule_order(probs: list[float], rnd) -> None:
    rules = [rule(f"r{i}", jev_body(qid=f"q{i}")) for i in range(len(probs))]
    answers = {f"q{i}": noul(p) for i, p in enumerate(probs)}
    shuffled = rules[:]
    rnd.shuffle(shuffled)
    a = asyncio.run(evaluate(rules, req(), FakeJev(answers=answers)))
    b = asyncio.run(evaluate(shuffled, req(), FakeJev(answers=answers)))
    assert a.verdict is b.verdict
