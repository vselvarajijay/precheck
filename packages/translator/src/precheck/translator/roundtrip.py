"""Round trip: translate eval cases with tests, run each generated test through the engine
against its own rule (Jev per JEV_MODE), and report the pass rate per case.

    python -m precheck.translator.roundtrip [CASE_ID ...]
"""

import argparse
import asyncio
import sys

from precheck.core.engine import EngineRule, evaluate
from precheck.core.jev import make_jev_client
from precheck.translator.eval import load_cases
from precheck.translator.llm import make_claude_client
from precheck.translator.pipeline import Translator
from precheck.translator.settings import get_tool_settings as get_settings


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*")
    args = parser.parse_args(argv)
    settings = get_settings()
    llm = make_claude_client(settings)
    total_pass = total = 0
    llm_cost = 0.0
    jev_tokens = 0
    async with make_jev_client(settings) as jev:
        for case in load_cases(args.cases or None):
            result = await Translator(llm).translate(case.input)
            llm_cost += result.cost_usd
            rules = {r.spec.id: r.spec for r in result.rules}
            passed = 0
            failures: list[str] = []
            for t in result.tests:
                spec = rules[t.rule_id]
                engine_rule = EngineRule(id=spec.id, gate=spec.gate, body=spec.body, version=1)
                decision = await evaluate([engine_rule], t.test.check_request, jev)
                jev_tokens += decision.usage.input_tokens
                if decision.verdict is t.test.expected_verdict:
                    passed += 1
                else:
                    failures.append(
                        f"{t.rule_id} [{t.kind}] {t.test.name!r}: "
                        f"expected {t.test.expected_verdict}, got {decision.verdict} "
                        f"({decision.rule_results[0].reason})"
                    )
            n = len(result.tests)
            total_pass += passed
            total += n
            rate = passed / n if n else 0.0
            print(
                f"{case.id:32} tests {passed}/{n} = {rate:.0%}  status={result.status} "
                f"${result.cost_usd:.4f}"
            )
            for f in failures:
                print(f"      ✗ {f}")
    rate = total_pass / total if total else 0.0
    print(f"overall {total_pass}/{total} = {rate:.0%} · LLM ${llm_cost:.4f} · Jev {jev_tokens} tok")
    return 0 if rate >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
