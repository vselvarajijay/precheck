from precheck.translator.llm import LLMError

from ..translator.conftest import FakeLLM, det_rule, draft_test, jev_rule, plan

BODY = {
    "text": "Refunds over $500 need a manager. Never refund to a different card.",
    "gate_hint": "tool_call",
    "tools": ["issue_refund"],
    "agent_purpose": "Support",
}
CLAR = [
    {
        "id": "approval",
        "question": "Escalate or require an approver field?",
        "options": ["escalate", "approver field"],
        "why": "unclear",
    }
]


def test_translate_returns_rules_and_stores_case(make_client) -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(), jev_rule()]}],
            "tests": [{"tests": [draft_test()]}],
        }
    )
    c = make_client(llm=llm)
    resp = c.post("/api/translate", json=BODY)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    result = data["result"]
    assert result["status"] == "translated"
    assert [r["spec"]["id"] for r in result["rules"]] == [
        "refund-over-limit",
        "refund-different-card",
    ]
    assert result["tests"][0]["test"]["expected_verdict"] == "escalate"
    assert result["provenance"]["translator_model"] == "fake-claude"
    stored = c.get(f"/api/translate/{data['business_case_id']}").json()
    assert stored["result"]["rules"] == result["rules"]


def test_clarification_then_answers(make_client) -> None:
    llm = FakeLLM(
        {
            "plan": [plan("needs_clarification", CLAR), plan()],
            "rules": [{"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    c = make_client(llm=llm)
    first = c.post("/api/translate", json=BODY).json()
    assert first["result"]["status"] == "needs_clarification"
    assert first["result"]["clarifications"][0]["id"] == "approval"
    case_id = first["business_case_id"]
    second = c.post(
        f"/api/translate/{case_id}/answers", json={"answers": {"approval": "escalate"}}
    ).json()
    assert second["business_case_id"] == case_id and second["result"]["status"] == "translated"
    assert "approval: escalate" in llm.calls[-3]["messages"][0]["content"]
    assert c.get(f"/api/translate/{case_id}").json()["result"]["status"] == "translated"


def test_translate_overlap_uses_existing_rules(make_client) -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(id="new-limit")]}],
            "tests": [{"tests": []}],
        }
    )
    c = make_client(llm=llm)
    body = {
        "deterministic": {
            "predicate": {"op": "gt", "path": "request.args.amount", "value": 1},
            "verdict_when_true": "deny",
        },
        "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"},
    }
    c.post("/api/rules", json={"id": "old-limit", "name": "old", "gate": "tool_call", "body": body})
    result = c.post("/api/translate", json=BODY).json()["result"]
    assert any("old-limit" in w["message"] for w in result["rules"][0]["warnings"])


def test_translator_errors_are_503_problem(make_client) -> None:
    class Broken(FakeLLM):
        async def complete_json(self, **kw):  # type: ignore[no-untyped-def]
            raise LLMError("Anthropic rate limit; try again shortly")

    c = make_client(llm=Broken({}))
    resp = c.post("/api/translate", json=BODY)
    assert resp.status_code == 503
    assert resp.json()["title"] == "Translator unavailable"


def test_answers_unknown_case_404_and_empty_422(make_client) -> None:
    c = make_client(llm=FakeLLM({}))
    assert c.post("/api/translate/nope/answers", json={"answers": {"a": "b"}}).status_code == 404
    assert c.post("/api/translate/nope/answers", json={"answers": {}}).status_code == 422
    assert c.post("/api/translate", json={"text": ""}).status_code == 422
