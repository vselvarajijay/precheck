"""Run every lab scenario (scripted) against a running stack and report pass/fail.

    python -m precheck.labagent.suite --api URL --proxy URL/mcp --tools URL [--prepare]

--prepare resets the database (test hook), seeds the demo pack live, reloads the proxy's
policy and clears the tools' call log first. Exit code 1 if any step fails.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from precheck.config import get_settings
from precheck.labagent.reporting import LabApi
from precheck.labagent.runner import run_scenario
from precheck.labagent.scenarios import load_scenarios


async def prepare(api: str, proxy_base: str, tools: str) -> None:
    async with httpx.AsyncClient(timeout=30) as http:
        (await http.post(f"{api}/api/testing/reset")).raise_for_status()
        (await http.post(f"{api}/api/testing/seed-demo")).raise_for_status()
        (await http.post(f"{proxy_base}/reload")).raise_for_status()
        (await http.post(f"{tools}/reset")).raise_for_status()


async def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=settings.api_url)
    parser.add_argument("--proxy", default=settings.agent_proxy_url)
    parser.add_argument("--tools", default=settings.agent_tools_url)
    parser.add_argument("--scenarios", type=Path, default=settings.examples_dir / "scenarios")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("only", nargs="*", help="scenario ids (default: all)")
    args = parser.parse_args(argv)
    if args.prepare:
        await prepare(args.api.rstrip("/"), args.proxy.removesuffix("/mcp"), args.tools.rstrip("/"))
    api = LabApi(args.api, args.tools)
    scenarios = [s for s in load_scenarios(args.scenarios) if not args.only or s.id in args.only]
    failed_steps = total_steps = 0
    print(
        f"{'scenario':22} {'step':4} {'tool':22} {'expected':10} {'actual':10} {'reached':8} result"
    )
    for scenario in scenarios:
        run = await run_scenario(scenario, args.proxy, api)
        if run.error:
            print(f"{scenario.id:22} ERROR {run.error}")
            failed_steps += 1
            continue
        for step in run.steps:
            total_steps += 1
            failed_steps += not step.passed
            actual = step.verdict.value if step.verdict else "-"
            if step.expected_result_verdict:
                actual += f"/{step.result_verdict.value if step.result_verdict else '-'}"
            expected = (step.expected_verdict.value if step.expected_verdict else "-") + (
                f"/{step.expected_result_verdict.value}" if step.expected_result_verdict else ""
            )
            jev = [
                f"{q}={o.value:.2f}"
                for d in step.decisions
                for r in (d.decision.rule_results if d.decision else [])
                for q, o in r.jev.items()
            ]
            result = "PASS" if step.passed else "FAIL " + "; ".join(step.mismatches)
            print(
                f"{scenario.id:22} {step.index:<4} {step.tool:22} {expected:10} {actual:10} "
                f"{step.reached_tool!s:8} {result}"
                f"  {step.latency_ms:.0f}ms {' '.join(jev)}"
            )
    print(f"\n{len(scenarios)} scenarios, {total_steps - failed_steps}/{total_steps} steps passed")
    return 1 if failed_steps else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
