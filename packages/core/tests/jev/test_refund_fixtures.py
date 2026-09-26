"""Replays the committed refund fixtures (recorded live 2026-09-26 with jev-1.13.0)."""

import pytest

from precheck.core.jev import FixtureStore, JevClient, build_calls, split_answers
from precheck.core.schema.loader import load_check_request, load_rule_pack
from precheck.core.settings import EXAMPLES_DIR, FIXTURES_DIR

EXAMPLES = EXAMPLES_DIR
FIXTURES = FixtureStore(FIXTURES_DIR / "jev")


@pytest.mark.parametrize(
    ("request_file", "high"),
    [
        ("refund-different-card.json", True),
        ("refund-over-500.json", False),
        ("refund-same-card-ok.json", False),
    ],
)
async def test_refund_fixture_replay(request_file: str, high: bool) -> None:
    rule = next(
        r
        for r in load_rule_pack(EXAMPLES / "refund.yaml").rules
        if r.id == "refund-different-payment-method"
    )
    assert rule.body.jev is not None
    data = load_check_request(EXAMPLES / "requests" / request_file).as_data()
    [call] = build_calls([(rule.id, rule.body.jev)], data)
    resp = await JevClient(None, mode="replay", fixtures=FIXTURES).evaluate(
        call.state, call.questions, call.model
    )
    answer = split_answers(call, resp)[rule.id]["different_method"]
    assert resp.resolved_model == "jev-1.13.0"
    assert (answer.noul > 0.7) is high  # type: ignore[union-attr]
