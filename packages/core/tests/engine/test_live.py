import pytest

from precheck.core.engine import evaluate, rules_from_pack
from precheck.core.jev import make_jev_client
from precheck.core.schema.loader import load_check_request, load_rule_pack
from precheck.core.settings import JevSettings as Settings

from .test_refund_replay import EXAMPLES, EXPECTED

pytestmark = pytest.mark.live


async def test_live_refund_example_verdicts() -> None:
    settings = Settings()
    if not settings.jev_configured:
        pytest.skip("TYPESAFE_API_KEY not configured")
    rules = rules_from_pack(load_rule_pack(EXAMPLES / "refund.yaml"))
    async with make_jev_client(settings, mode="live") as jev:
        for name, expected in EXPECTED.items():
            d = await evaluate(
                rules, load_check_request(EXAMPLES / "requests" / f"{name}.json"), jev
            )
            assert d.verdict is expected, name
            assert d.latency_ms < 1000
