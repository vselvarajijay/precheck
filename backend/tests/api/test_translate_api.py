import json

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


def _translated(make_client):
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(), jev_rule()]}],
            "tests": [
                {
                    "tests": [
                        draft_test(),
                        draft_test("refund-different-card", expected_verdict="deny"),
                    ]
                }
            ],
        }
    )
    c = make_client(llm=llm)
    data = c.post("/api/translate", json=BODY).json()
    return c, llm, data


def test_stream_emits_progress_then_result(make_client) -> None:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(id="Bad Id")]}, {"rules": [det_rule()]}],
            "tests": [{"tests": []}],
        }
    )
    c = make_client(llm=llm)
    with c.stream("POST", "/api/translate/stream", json=BODY) as resp:
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in resp.iter_lines() if line]
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert stages == ["plan", "rules", "validating", "repairing", "rules", "validating", "tests"]
    result = events[-1]
    assert result["type"] == "result" and result["data"]["result"]["status"] == "translated"
    assert c.get(f"/api/translate/{result['data']['business_case_id']}").status_code == 200


def test_stream_reports_llm_errors(make_client) -> None:
    class Broken(FakeLLM):
        async def complete_json(self, **kw):  # type: ignore[no-untyped-def]
            raise LLMError("Anthropic rate limit; try again shortly")

    c = make_client(llm=Broken({}))
    with c.stream("POST", "/api/translate/stream", json=BODY) as resp:
        events = [json.loads(line) for line in resp.iter_lines() if line]
    assert events[-1] == {
        "type": "error",
        "status": 503,
        "detail": "Anthropic rate limit; try again shortly",
    }


def test_save_creates_drafts_with_provenance_and_tests(make_client) -> None:
    c, _, data = _translated(make_client)
    result = data["result"]
    # An existing rule with the same id forces a suffix; tests follow the new id.
    c.post(
        "/api/rules",
        json={
            "id": "refund-over-limit",
            "name": "old",
            "gate": "tool_call",
            "body": {
                "deterministic": {
                    "predicate": {"op": "exists", "path": "reason"},
                    "verdict_when_true": "deny",
                }
            },
        },
    )
    edited = result["rules"][0]["spec"] | {"name": "Refund over limit (edited)"}
    payload = {
        "rules": [edited, result["rules"][1]["spec"]],
        "tests": [{"rule_id": t["rule_id"], "test": t["test"]} for t in result["tests"]],
    }
    saved = c.post(f"/api/translate/{data['business_case_id']}/save", json=payload)
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["rules"] == [
        {"requested_id": "refund-over-limit", "id": "refund-over-limit-2"},
        {"requested_id": "refund-different-card", "id": "refund-different-card"},
    ]
    assert body["tests_created"] == 2
    rule = c.get("/api/rules/refund-over-limit-2").json()
    assert rule["name"] == "Refund over limit (edited)" and rule["status"] == "draft"
    assert rule["current"]["translator_model"] == "fake-claude"
    assert rule["current"]["prompt_version"].startswith("translate_v1+")
    assert [t["origin"] for t in c.get("/api/rules/refund-over-limit-2/test-cases").json()] == [
        "generated"
    ]
    assert len(c.get("/api/rules/refund-different-card/test-cases").json()) == 1


def test_refine_returns_one_rule(make_client) -> None:
    refined = det_rule(explanation="Refunds over $200 wait for a human.")
    refined["deterministic"]["conditions"][0]["value_number"] = 200
    llm = FakeLLM({"rules": [{"rules": [refined]}]})
    c = make_client(llm=llm)
    spec = {
        "id": "refund-over-limit",
        "name": "Refund over limit",
        "gate": "tool_call",
        "source_text": "x",
        "body": {
            "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"},
            "deterministic": {
                "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
                "verdict_when_true": "escalate",
            },
        },
    }
    resp = c.post(
        "/api/translate/refine", json={"rule": spec, "instruction": "Lower the limit to $200"}
    ).json()
    assert resp["errors"] == []
    assert resp["rule"]["spec"]["body"]["deterministic"]["predicate"]["value"] == 200
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "Lower the limit to $200" in prompt and '"value_number": 500' in prompt


def test_refine_rejects_nested_groups(make_client) -> None:
    c = make_client(llm=FakeLLM({}))
    spec = {
        "id": "r",
        "name": "R",
        "gate": "tool_call",
        "body": {
            "deterministic": {
                "predicate": {
                    "op": "all",
                    "predicates": [
                        {"op": "any", "predicates": [{"op": "exists", "path": "reason"}]}
                    ],
                },
                "verdict_when_true": "deny",
            }
        },
    }
    resp = c.post("/api/translate/refine", json={"rule": spec, "instruction": "x"}).json()
    assert resp["rule"] is None and "nested condition groups" in resp["errors"][0]


def test_evaluate_inline_scope(make_client) -> None:
    c = make_client(llm=FakeLLM({}))
    spec = {
        "id": "limit",
        "name": "Limit",
        "gate": "tool_call",
        "body": {
            "deterministic": {
                "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
                "verdict_when_true": "escalate",
            }
        },
    }
    req = {
        "gate": "tool_call",
        "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 900}},
    }
    out = c.post(
        "/api/evaluate",
        json={"check_request": req, "scope": {"kind": "inline", "inline_rules": [spec]}},
    ).json()
    assert out["decision"]["verdict"] == "escalate" and out["rules"]["limit"]["version"] == 0
    assert c.get("/api/rules").json() == []  # nothing stored
    assert (
        c.post(
            "/api/evaluate", json={"check_request": req, "scope": {"kind": "inline"}}
        ).status_code
        == 422
    )
