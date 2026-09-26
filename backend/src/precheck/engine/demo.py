"""Evaluate example requests against a rule pack and print the decisions.

    python -m precheck.engine.demo examples/refund.yaml examples/requests/*.json

Uses JEV_MODE from settings (live by default; replay to use recorded fixtures).
"""

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from precheck.config import get_settings
from precheck.engine.evaluate import evaluate, rules_from_pack
from precheck.jev import make_jev_client
from precheck.schema.loader import load_check_request, load_rule_pack


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("requests", nargs="+", type=Path)
    args = parser.parse_args(argv)
    rules = rules_from_pack(load_rule_pack(args.pack))
    settings = get_settings()
    latencies: list[float] = []
    async with make_jev_client(settings) as jev:
        for path in args.requests:
            decision = await evaluate(rules, load_check_request(path), jev)
            latencies.append(decision.latency_ms)
            print(
                f"{path.stem}: {decision.verdict.upper()}  ({decision.latency_ms:.0f} ms, "
                f"{decision.usage.input_tokens} tok, jev={decision.versions.jev_model})"
            )
            for r in decision.rule_results:
                if not r.matched:
                    continue
                verdict = r.verdict.value if r.verdict else "-"
                print(f"    {r.rule_id}: {verdict} [{r.source}] {r.reason}")
                if r.predicate_inputs:
                    print(f"        inputs {r.predicate_inputs}")
    print(f"p50 latency: {statistics.median(latencies):.0f} ms (mode={settings.jev_mode})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
