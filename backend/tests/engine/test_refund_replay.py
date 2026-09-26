"""Refund example end to end against recorded Jev fixtures."""

from pathlib import Path

import pytest

from precheck.engine import evaluate, rules_from_pack
from precheck.jev import FixtureStore, JevClient
from precheck.schema import Verdict
from precheck.schema.loader import load_check_request, load_rule_pack

BACKEND = Path(__file__).resolve().parents[2]
EXAMPLES = BACKEND / "examples"
EXPECTED = {
    "refund-different-card": Verdict.deny,
    "refund-over-500": Verdict.escalate,
    "refund-same-card-ok": Verdict.allow,
    "missing-reason": Verdict.escalate,
}


@pytest.mark.parametrize(("name", "expected"), EXPECTED.items())
async def test_refund_example_replay(name: str, expected: Verdict) -> None:
    rules = rules_from_pack(load_rule_pack(EXAMPLES / "refund.yaml"))
    jev = JevClient(None, mode="replay", fixtures=FixtureStore(BACKEND / "tests/fixtures/jev"))
    decision = await evaluate(
        rules, load_check_request(EXAMPLES / "requests" / f"{name}.json"), jev
    )
    assert decision.verdict is expected
