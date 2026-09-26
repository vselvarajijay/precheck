"""Live smoke test: `python -m precheck.jev.smoke` (one tiny call, ~500 tokens)."""

import asyncio
import sys

from precheck.config import get_settings
from precheck.jev.client import make_jev_client
from precheck.schema import ChoiceQuestion, JevQuestion, NoulQuestion, ScoreQuestion

STATE = {
    "request": {"tool": "issue_refund", "args": {"amount": 120, "destination": "Mastercard 9911"}},
    "history": [{"tool": "lookup_order", "result_summary": "Order $120.00, paid with Visa 4242"}],
}
QUESTIONS: dict[str, JevQuestion] = {
    "smoke__different_method": NoulQuestion(
        type="noul",
        instructions="Does this refund send money to a payment method different from the one "
        "used for the original purchase?",
    ),
    "smoke__action": ChoiceQuestion(
        type="choice",
        instructions="What kind of action is the request?",
        criteria={"refund": "Returns money to a customer", "lookup": "Reads data only"},
    ),
    "smoke__risk": ScoreQuestion(
        type="score",
        instructions="How risky is this action?",
        criteria=["routine", "needs care", "dangerous"],
    ),
}


async def main() -> int:
    settings = get_settings()
    if not settings.jev_configured:
        print("TYPESAFE_API_KEY is not configured", file=sys.stderr)
        return 1
    async with make_jev_client(settings, mode="live") as client:
        resp = await client.evaluate(STATE, QUESTIONS, "jev-latest")
    print(f"model:      {resp.resolved_model}")
    print(f"latency_ms: {resp.latency_ms:.0f}")
    print(f"tokens:     in={resp.usage.input_tokens} out={resp.usage.output_tokens}")
    print(f"request_id: {resp.request_id}")
    for qid, ans in resp.answers.items():
        print(f"  {qid}: {ans.model_dump(exclude={'legend', 'probabilities'})}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
