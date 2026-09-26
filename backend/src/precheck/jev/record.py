"""Record Jev fixtures for a rule pack + example requests (costs a few hundred tokens each).

    python -m precheck.jev.record examples/refund.yaml examples/requests/*.json

Builds the same calls the engine makes for applicable Jev checks (gate, applies_when and
requires satisfied) and saves responses under JEV_FIXTURES_DIR.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from precheck.config import get_settings
from precheck.jev.batch import build_calls
from precheck.jev.client import make_jev_client
from precheck.schema import JevCheck, evaluate_predicate, resolve
from precheck.schema.loader import load_check_request, load_rule_pack


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("requests", nargs="+", type=Path)
    args = parser.parse_args(argv)
    pack = load_rule_pack(args.pack)
    settings = get_settings()
    total = 0
    async with make_jev_client(settings, mode="record") as client:
        for path in args.requests:
            cr = load_check_request(path)
            data = cr.as_data()
            checks: list[tuple[str, JevCheck]] = []
            for rule in pack.rules:
                body = rule.body
                if rule.gate != cr.gate or body.jev is None:
                    continue
                if body.applies_when and not evaluate_predicate(body.applies_when, data):
                    continue
                if any(resolve(data, p).missing for p in body.requires):
                    continue
                checks.append((rule.id, body.jev))
            for call in build_calls(checks, data):
                resp = await client.evaluate(call.state, call.questions, call.model)
                total += resp.usage.input_tokens
                print(
                    f"{path.name}: {call.rule_ids} -> {resp.resolved_model} "
                    f"{resp.usage.input_tokens} tok {resp.latency_ms:.0f} ms"
                )
    print(f"total input tokens: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
