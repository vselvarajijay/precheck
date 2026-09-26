"""Translator eval: run the corpus and score each result's shape.

    python -m precheck.translator.eval [--tests] [CASE_ID ...]

LLM_MODE decides live / record / replay. Assertions per case (all optional):
rules (count, ±1), numeric_predicate, jev, domain_predicate (presence), requires (fields
declared), clarification (asked for one). Prints a table, the score and the LLM cost.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from precheck.config import get_settings
from precheck.schema import RuleSpec
from precheck.schema.predicate import AllPredicate, AnyPredicate, NotPredicate
from precheck.translator.llm import make_claude_client
from precheck.translator.pipeline import TranslateInput, TranslationResult, Translator

CASES_DIR = Path(__file__).resolve().parents[3] / "tests" / "translator_eval" / "cases"


class EvalCase(BaseModel):
    id: str
    input: TranslateInput
    expect: dict[str, Any]


def load_cases(ids: list[str] | None = None) -> list[EvalCase]:
    cases = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        if ids and f.stem not in ids:
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        expect = data.pop("expect")
        cases.append(EvalCase(id=f.stem, input=TranslateInput.model_validate(data), expect=expect))
    return cases


def _ops(pred: Any) -> set[str]:
    if isinstance(pred, AllPredicate | AnyPredicate):
        return {o for c in pred.predicates for o in _ops(c)} | {pred.op}
    if isinstance(pred, NotPredicate):
        return _ops(pred.predicate) | {"not"}
    return {pred.op}


def check_shape(result: TranslationResult, expect: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """(assertion, passed, detail) for every expectation."""
    specs: list[RuleSpec] = [r.spec for r in result.rules]
    det_ops = {
        o for s in specs if s.body.deterministic for o in _ops(s.body.deterministic.predicate)
    }
    out: list[tuple[str, bool, str]] = []
    if "rules" in expect:
        n = len(specs)
        out.append(("rules", abs(n - expect["rules"]) <= 1, f"{n} (want {expect['rules']}±1)"))
    if "numeric_predicate" in expect:
        has = bool(det_ops & {"gt", "gte", "lt", "lte", "min_len"})
        out.append(
            ("numeric_predicate", has == expect["numeric_predicate"], f"ops {sorted(det_ops)}")
        )
    if "domain_predicate" in expect:
        has = bool(det_ops & {"domain_in", "domain_not_in"})
        out.append(
            ("domain_predicate", has == expect["domain_predicate"], f"ops {sorted(det_ops)}")
        )
    if "jev" in expect:
        has = any(s.body.jev for s in specs)
        out.append(("jev", has == expect["jev"], f"jev={has}"))
    if "requires" in expect:
        declared = {p for s in specs for p in s.body.requires}
        missing = [p for p in expect["requires"] if p not in declared]
        out.append(("requires", not missing, f"declared {sorted(declared)}"))
    if expect.get("clarification"):
        asked = result.status == "needs_clarification" or bool(result.clarifications)
        out.append(
            ("clarification", asked, f"status {result.status}, {len(result.clarifications)} q")
        )
    return out


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*")
    parser.add_argument("--tests", action="store_true", help="also generate tests (costs more)")
    args = parser.parse_args(argv)
    settings = get_settings()
    llm = make_claude_client(settings)
    passed = total = 0
    cost = 0.0
    print(f"model {llm.model} · mode {llm.mode} · effort {llm.effort}")
    for case in load_cases(args.cases or None):
        result = await Translator(llm, generate_tests=args.tests).translate(case.input)
        cost += result.cost_usd
        checks = check_shape(result, case.expect)
        ok = sum(p for _, p, _ in checks)
        passed += ok
        total += len(checks)
        mark = "PASS" if ok == len(checks) else "FAIL"
        print(
            f"{mark} {case.id:32} {ok}/{len(checks)}  status={result.status:20} "
            f"rules={len(result.rules)} repairs={result.repair_rounds} ${result.cost_usd:.4f}"
        )
        for name, p, detail in checks:
            if not p:
                print(f"      ✗ {name}: {detail}")
        for e in result.errors:
            print(f"      error: {e}")
    score = passed / total if total else 0.0
    print(f"score {passed}/{total} = {score:.0%} · LLM cost ${cost:.4f}")
    return 0 if score >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
