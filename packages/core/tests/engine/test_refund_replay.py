"""Refund example end to end against recorded Jev fixtures."""

import pytest

from precheck.core.engine import evaluate, rules_from_pack
from precheck.core.jev import FixtureStore, JevClient
from precheck.core.schema import Verdict
from precheck.core.schema.loader import load_check_request, load_rule_pack
from precheck.core.settings import EXAMPLES_DIR, FIXTURES_DIR

EXAMPLES = EXAMPLES_DIR
EXPECTED = {
    "refund-different-card": Verdict.deny,
    "refund-over-500": Verdict.escalate,
    "refund-same-card-ok": Verdict.allow,
    "missing-reason": Verdict.escalate,
}


@pytest.mark.parametrize(("name", "expected"), EXPECTED.items())
async def test_refund_example_replay(name: str, expected: Verdict) -> None:
    rules = rules_from_pack(load_rule_pack(EXAMPLES / "refund.yaml"))
    jev = JevClient(None, mode="replay", fixtures=FixtureStore(FIXTURES_DIR / "jev"))
    decision = await evaluate(
        rules, load_check_request(EXAMPLES / "requests" / f"{name}.json"), jev
    )
    assert decision.verdict is expected
