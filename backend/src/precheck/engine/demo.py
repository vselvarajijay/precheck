"""Evaluate example requests against a rule pack and print the decisions.

    python -m precheck.engine.demo examples/refund.yaml examples/requests/*.json
    python -m precheck.engine.demo examples/rulepacks/demo.yaml examples/playground/*.json

Accepts bare check requests or playground examples ({check_request, expected_verdict});
exits non-zero if any example's verdict differs from its expectation. Uses JEV_MODE from
settings (live by default; replay uses fixtures; record saves them).
"""

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

from precheck.config import get_settings
from precheck.engine.evaluate import evaluate, rules_from_pack
from precheck.jev import make_jev_client
from precheck.schema import CheckRequest, Verdict
from precheck.schema.loader import load_data, load_rule_pack


def _load(path: Path) -> tuple[CheckRequest, Verdict | None]:
    data = load_data(path)
    if isinstance(data, dict) and "check_request" in data:
        expected = data.get("expected_verdict")
        request = CheckRequest.model_validate(data["check_request"])
        return request, Verdict(expected) if expected else None
    return CheckRequest.model_validate(data), None


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("requests", nargs="+", type=Path)
    args = parser.parse_args(argv)
    rules = rules_from_pack(load_rule_pack(args.pack))
    settings = get_settings()
    latencies: list[float] = []
    mismatches = 0
    async with make_jev_client(settings) as jev:
        for path in args.requests:
            check_request, expected = _load(path)
            decision = await evaluate(rules, check_request, jev)
            latencies.append(decision.latency_ms)
            note = ""
            if expected is not None:
                ok = decision.verdict is expected
                mismatches += not ok
                note = f"  expected {expected.upper()} {'ok' if ok else 'MISMATCH'}"
            print(
                f"{path.stem}: {decision.verdict.upper()}{note}  ({decision.latency_ms:.0f} ms, "
                f"{decision.usage.input_tokens} tok, jev={decision.versions.jev_model})"
            )
            for r in decision.rule_results:
                if not r.matched:
                    continue
                verdict = r.verdict.value if r.verdict else "-"
                print(f"    {r.rule_id}: {verdict} [{r.source}] {r.reason}")
                if r.predicate_inputs:
                    print(f"        inputs {r.predicate_inputs}")
                for qid, q in r.jev.items():
                    print(f"        {qid}: value={q.value:.2f} -> {q.verdict} ({q.band})")
    print(f"p50 latency: {statistics.median(latencies):.0f} ms (mode={settings.jev_mode})")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
