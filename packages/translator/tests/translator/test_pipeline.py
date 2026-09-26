import pytest

from precheck.core.schema import Gate
from precheck.translator.lints import ExistingRule
from precheck.translator.pipeline import MAX_REPAIR_ROUNDS, TranslateInput, Translator, load_prompt

from .conftest import FakeLLM, det_rule, draft_test, jev_rule, plan

INP = TranslateInput(
    text="Refunds over $500 need a manager. Never refund to a different card.",
    gate_hint="tool_call",
    tools=["issue_refund"],
    agent_purpose="Support",
)


async def test_pipeline_wiring_plan_rules_tests() -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(), jev_rule()]}],
            "tests": [
                {
                    "tests": [
                        draft_test(),
                        draft_test(
                            "refund-different-card",
                            expected_verdict="deny",
                            history=[
                                {
                                    "tool": "lookup_order",
                                    "args_json": "{}",
                                    "result_summary": "Visa 4242",
                                }
                            ],
                        ),
                    ]
                }
            ],
        }
    )
    r = await Translator(llm).translate(INP)
    assert llm.steps() == ["plan", "rules", "tests"]
    assert r.status == "translated" and r.errors == [] and r.repair_rounds == 0
    assert [t.spec.id for t in r.rules] == ["refund-over-limit", "refund-different-card"]
    det = r.rules[0].spec.body.deterministic
    assert det is not None and det.predicate.model_dump() == {
        "op": "gt",
        "path": "request.args.amount",
        "value": 500.0,
    }
    assert r.rules[0].spec.body.applies_when.model_dump() == {
        "op": "eq",
        "path": "request.tool",
        "value": "issue_refund",
    }  # type: ignore[union-attr]
    jev = r.rules[1].spec.body.jev
    assert (
        jev is not None
        and jev.model == "jev-latest"
        and jev.outcomes["different_method"].bands.deny_at == 0.6
    )  # type: ignore[union-attr]
    assert [t.test.expected_verdict.value for t in r.tests] == ["escalate", "deny"]
    cr = r.tests[1].test.check_request
    assert (
        cr.gate.value == "tool_call"
        and cr.agent.purpose == "Support"
        and cr.history[0].tool == "lookup_order"
    )  # type: ignore[union-attr,index]
    # The rules step sees the plan; the tests step sees the rules.
    assert "Plan from step 1" in llm.calls[1]["messages"][0]["content"]
    assert "Rules from step 2" in llm.calls[2]["messages"][0]["content"]


async def test_provenance_and_usage_filled() -> None:
    llm = FakeLLM({"plan": [plan()], "rules": [{"rules": [det_rule()]}], "tests": [{"tests": []}]})
    r = await Translator(llm).translate(INP)
    _, version = load_prompt()
    assert r.provenance.translator_model == "fake-claude"
    assert r.provenance.prompt_version == version and version.startswith("translate_v1+")
    assert r.provenance.code_version
    assert r.usage.input_tokens == 3000 and r.cost_usd > 0


async def test_repair_loop_fixes_invalid_rules() -> None:
    bad = det_rule(id="Bad Id")  # invalid rule id
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [bad]}, {"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    r = await Translator(llm).translate(INP)
    assert llm.steps() == ["plan", "rules", "rules", "tests"]
    assert r.repair_rounds == 1 and r.errors == [] and r.status == "translated"
    repair_prompt = llm.calls[2]["messages"][-1]["content"]
    assert "failed validation" in repair_prompt and "Bad Id" in repair_prompt
    assert llm.calls[2]["messages"][1]["role"] == "assistant"


async def test_repair_loop_stops_after_max_rounds() -> None:
    llm = FakeLLM(
        {"plan": [plan()], "rules": [{"rules": [det_rule(id="Bad Id")]}], "tests": [{"tests": []}]}
    )
    r = await Translator(llm).translate(INP)
    assert llm.steps().count("rules") == 1 + MAX_REPAIR_ROUNDS == 3
    assert r.repair_rounds == MAX_REPAIR_ROUNDS
    assert r.errors and "String should match pattern" in r.errors[0]
    assert r.status == "failed" and "tests" not in llm.steps()


async def test_repair_loop_semantic_no_effect_allow() -> None:
    useless = det_rule(
        deterministic={
            "combine": "all",
            "negate": False,
            "verdict_when_true": "allow",
            "conditions": [
                {
                    "path": "reason",
                    "op": "min_len",
                    "value_text": None,
                    "value_number": 5,
                    "values": [],
                    "domains": [],
                }
            ],
        }
    )
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [useless]}, {"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    r = await Translator(llm).translate(INP)
    assert r.repair_rounds == 1
    assert "has no effect" in llm.calls[2]["messages"][-1]["content"]


async def test_repair_loop_egress_rule_on_tool_fields_goes_to_tool_call() -> None:
    """Enforcement checks catalog tools (http_request, send_email) at tool_call; an egress rule
    matching request.tool / request.args would never fire."""
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(gate="egress")]}, {"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    r = await Translator(llm).translate(INP)
    assert r.repair_rounds == 1
    feedback = llm.calls[2]["messages"][-1]["content"]
    assert "gate is egress but the rule matches on request.args.amount, request.tool" in feedback
    assert r.rules[0].spec.gate == "tool_call"


async def test_egress_hint_keeps_egress_rule_with_a_review_warning() -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(gate="egress")]}],
            "tests": [{"tests": []}],
        }
    )
    r = await Translator(llm).translate(INP.model_copy(update={"gate_hint": Gate.egress}))
    assert r.repair_rounds == 0 and r.rules[0].spec.gate == "egress"
    assert "gate_not_enforced" in [w.code for w in r.rules[0].warnings]


async def test_clarification_stops_after_plan_and_answers_resume() -> None:
    clar = [
        {
            "id": "approval",
            "question": "Escalate or require an approver field?",
            "options": ["escalate to a human", "require approver_id in args"],
            "why": "unclear signal",
        }
    ]
    llm = FakeLLM(
        {
            "plan": [plan("needs_clarification", clar)],
            "rules": [{"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    r = await Translator(llm).translate(INP)
    assert r.status == "needs_clarification" and r.rules == [] and llm.steps() == ["plan"]
    assert r.clarifications[0].id == "approval"

    llm2 = FakeLLM({"plan": [plan()], "rules": [{"rules": [det_rule()]}], "tests": [{"tests": []}]})
    answered = INP.model_copy(update={"answers": {"approval": "escalate to a human"}})
    r2 = await Translator(llm2).translate(answered)
    assert r2.status == "translated"
    assert "approval: escalate to a human" in llm2.calls[0]["messages"][0]["content"]
    assert "do not ask again" in llm2.calls[0]["messages"][0]["content"]


async def test_invalid_tests_dropped_with_warning() -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule()]}],
            "tests": [
                {"tests": [draft_test(), draft_test(args_json="not json"), draft_test("nope")]}
            ],
        }
    )
    r = await Translator(llm).translate(INP)
    assert len(r.tests) == 1
    codes = [w.message for w in r.warnings if w.code == "invalid_test"]
    assert any("invalid JSON" in m for m in codes) and any("unknown rule_id" in m for m in codes)


async def test_plan_schema_mismatch_fails_cleanly() -> None:
    r = await Translator(FakeLLM({"plan": ["{not json"]})).translate(INP)
    assert r.status == "failed" and "plan did not match" in r.errors[0]


async def test_generate_tests_off_skips_step() -> None:
    llm = FakeLLM({"plan": [plan()], "rules": [{"rules": [det_rule()]}], "tests": [{"tests": []}]})
    r = await Translator(llm, generate_tests=False).translate(INP)
    assert llm.steps() == ["plan", "rules"] and r.status == "translated"


@pytest.mark.parametrize(
    ("negate", "combine", "expected"),
    [
        (False, "all", {"op": "gt", "path": "request.args.amount", "value": 500.0}),
        (
            True,
            "all",
            {"op": "not", "predicate": {"op": "gt", "path": "request.args.amount", "value": 500.0}},
        ),
    ],
)
async def test_condition_negate(negate: bool, combine: str, expected: dict) -> None:
    rule = det_rule()
    rule["deterministic"]["negate"] = negate
    llm = FakeLLM({"plan": [plan()], "rules": [{"rules": [rule]}], "tests": [{"tests": []}]})
    r = await Translator(llm, generate_tests=False).translate(INP)
    assert r.rules[0].spec.body.deterministic.predicate.model_dump() == expected  # type: ignore[union-attr]


async def test_overlap_with_existing_rule_warns() -> None:
    llm = FakeLLM({"plan": [plan()], "rules": [{"rules": [det_rule()]}], "tests": [{"tests": []}]})
    existing = [ExistingRule(id="old-refund-rule", gate="tool_call", tools=["issue_refund"])]
    r = await Translator(llm, existing=existing, generate_tests=False).translate(INP)
    assert any(
        w.code == "possible_overlap" and "old-refund-rule" in w.message for w in r.rules[0].warnings
    )
