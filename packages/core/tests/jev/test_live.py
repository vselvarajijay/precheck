"""Real Jev calls. Run with `make test-live ARGS='-k jev'` (needs TYPESAFE_API_KEY)."""

import re

import pytest

from precheck.core.jev import JevClient, make_jev_client
from precheck.core.settings import JevSettings as Settings
from precheck.server.devtools.jev_smoke import QUESTIONS, STATE

pytestmark = pytest.mark.live


@pytest.fixture
async def live_client():
    settings = Settings()
    if not settings.jev_configured:
        pytest.skip("TYPESAFE_API_KEY not configured")
    async with make_jev_client(settings, mode="live") as client:
        yield client


async def test_live_jev_round_trip_all_types(live_client: JevClient) -> None:
    # Also proves `<rule>__<question>` ids (with hyphens) are accepted.
    questions = {f"live-rule__{k.split('__')[1]}": v for k, v in QUESTIONS.items()}
    resp = await live_client.evaluate(STATE, questions, "jev-latest")
    assert re.fullmatch(r"jev-\d+\.\d+\.\d+", resp.resolved_model)
    assert set(resp.answers) == set(questions)
    types = {a.type for a in resp.answers.values()}
    assert types == {"noul", "choice", "score"}
    assert resp.usage.input_tokens > 0
    assert resp.latency_ms < 5000


async def test_live_jev_resolve_model(live_client: JevClient) -> None:
    assert re.fullmatch(r"jev-\d+\.\d+\.\d+", await live_client.resolve_model("jev-latest"))
