"""The translator eval corpus replayed from fixtures recorded live (claude-sonnet-5,
2026-09-26). Guards against regressions in conversion/validation without LLM calls.
Re-record with `make eval-translator` after changing the prompt or draft schema."""

import pytest

from precheck.core.settings import FIXTURES_DIR
from precheck.translator.eval import check_shape, load_cases
from precheck.translator.llm import ClaudeClient
from precheck.translator.pipeline import Translator

FIXTURES = FIXTURES_DIR / "llm"
LLM = ClaudeClient(
    None, model="claude-sonnet-5", effort="low", mode="replay", fixtures_dir=FIXTURES
)


async def test_eval_corpus_shape_score_replayed() -> None:
    passed = total = 0
    for case in load_cases():
        result = await Translator(LLM, generate_tests=False).translate(case.input)
        checks = check_shape(result, case.expect)
        passed += sum(p for _, p, _ in checks)
        total += len(checks)
    assert total >= 30
    assert passed / total >= 0.8


@pytest.mark.parametrize(
    "case_id", ["01-refund-limit-card-reason", "02-pii-egress", "04-api-allowlist", "10-discounts"]
)
async def test_generated_tests_replayed(case_id: str) -> None:
    [case] = load_cases([case_id])
    result = await Translator(LLM).translate(case.input)
    assert result.status == "translated" and result.tests
    rule_ids = {r.spec.id for r in result.rules}
    assert all(t.rule_id in rule_ids for t in result.tests)
    assert {t.kind for t in result.tests} >= {"positive", "negative"}
