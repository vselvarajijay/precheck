"""In-process MCP client against precheck-authoring (`pytest -k mcp`)."""

import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from precheck.core.testing import FakeJev, noul
from precheck.server.db.engine import make_engine, session_factory
from precheck.server.mcp.authoring import Deps, build_server
from precheck.translator.testing import FakeLLM, det_rule, draft_test, jev_rule, plan

REQ = {
    "gate": "tool_call",
    "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 620}},
    "reason": "damaged item",
}
SPEC = {
    "id": "refund-over-limit",
    "name": "Refund over limit",
    "gate": "tool_call",
    "source_text": "Refunds over $500 need a manager.",
    "body": {
        "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"},
        "deterministic": {
            "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
            "verdict_when_true": "escalate",
        },
    },
    "tests": [{"name": "big", "check_request": REQ, "expected_verdict": "escalate"}],
}


@pytest.fixture
def deps(db_path: Path) -> Deps:
    llm = FakeLLM(
        {
            "plan": [plan()],
            "rules": [{"rules": [det_rule(), jev_rule()]}],
            "tests": [{"tests": [draft_test()]}],
        }
    )
    return Deps(
        db=session_factory(make_engine(db_path)),
        jev=FakeJev(answers={"different_method": noul(0.1)}),
        llm=llm,
    )


def data(result: Any) -> Any:
    assert not result.is_error, result.content
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(result.content[0].text)


async def test_mcp_no_publish_tool(deps: Deps) -> None:
    async with Client(build_server(deps)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        "list_rules",
        "get_rule",
        "translate_business_case",
        "answer_clarifications",
        "evaluate_request",
        "run_tests",
        "propose_rule_change",
    }
    forbidden = ("publish", "live", "status", "activate", "delete", "archive")
    assert not [n for n in tools if any(f in n for f in forbidden)]
    assert "can never make anything live" in tools["propose_rule_change"].description
    assert (
        '"gate": "tool_call"' in tools["evaluate_request"].description
    )  # check-request shape documented


async def test_mcp_propose_then_evaluate_and_test(deps: Deps, make_client) -> None:
    async with Client(build_server(deps)) as client:
        proposed = data(await client.call_tool("propose_rule_change", {"rule": SPEC}))
        assert (
            proposed["created_new_rule"]
            and proposed["status"] == "draft"
            and proposed["tests_created"] == 1
        )
        listed = data(await client.call_tool("list_rules", {}))
        assert [r["id"] for r in listed] == ["refund-over-limit"] and listed[0][
            "created_by"
        ] == "agent"
        detail = data(await client.call_tool("get_rule", {"rule_id": "refund-over-limit"}))
        assert detail["current"]["body"]["deterministic"]["predicate"]["value"] == 500
        # Draft scope sees it; live scope (default) doesn't — agents can't make it live.
        live = data(await client.call_tool("evaluate_request", {"check_request": REQ}))
        assert live["decision"]["verdict"] == "allow" and live["decision"]["gate_default_applied"]
        draft = data(
            await client.call_tool("evaluate_request", {"check_request": REQ, "scope": "draft"})
        )
        assert draft["decision"]["verdict"] == "escalate"
        run = data(await client.call_tool("run_tests", {"rule_id": "refund-over-limit"}))
        assert run["pass_count"] == 1
        # A second proposal for the same id becomes a new draft version.
        changed = {
            **SPEC,
            "tests": [],
            "body": {
                **SPEC["body"],
                "deterministic": {
                    **SPEC["body"]["deterministic"],
                    "predicate": {"op": "gt", "path": "request.args.amount", "value": 200},
                },
            },
        }
        again = data(await client.call_tool("propose_rule_change", {"rule": changed}))
        assert not again["created_new_rule"] and again["version"] == 2
    # Visible through the HTTP API with created_by=agent.
    api = make_client().get("/api/rules/refund-over-limit").json()
    assert api["created_by"] == "agent" and api["status"] == "draft" and api["current_version"] == 2


async def test_mcp_translate_and_answer(deps: Deps) -> None:
    async with Client(build_server(deps)) as client:
        out = data(
            await client.call_tool(
                "translate_business_case",
                {
                    "text": "Refunds over $500 need a manager.",
                    "gate_hint": "tool_call",
                    "tools": ["issue_refund"],
                },
            )
        )
        assert out["result"]["status"] == "translated" and len(out["result"]["rules"]) == 2
        spec = out["result"]["rules"][0]["spec"]
        assert data(await client.call_tool("propose_rule_change", {"rule": spec}))[
            "created_new_rule"
        ]
        again = data(
            await client.call_tool(
                "answer_clarifications",
                {"business_case_id": out["business_case_id"], "answers": {"approval": "escalate"}},
            )
        )
        assert again["business_case_id"] == out["business_case_id"]


async def test_mcp_evaluate_matches_playground(deps: Deps, make_client) -> None:
    async with Client(build_server(deps)) as client:
        await client.call_tool("propose_rule_change", {"rule": SPEC})
        via_mcp = data(
            await client.call_tool("evaluate_request", {"check_request": REQ, "scope": "draft"})
        )
    via_api = (
        make_client(jev=deps.jev)
        .post("/api/evaluate", json={"check_request": REQ, "scope": {"kind": "draft"}})
        .json()
    )
    assert via_mcp["decision"]["verdict"] == via_api["decision"]["verdict"] == "escalate"
    assert via_mcp["decision"]["rule_results"] == via_api["decision"]["rule_results"]


async def test_mcp_errors_are_tool_errors(deps: Deps) -> None:
    async with Client(build_server(deps)) as client:
        missing = await client.call_tool("get_rule", {"rule_id": "nope"})
        assert missing.is_error and "not found" in missing.content[0].text
        bad = await client.call_tool("propose_rule_change", {"rule": {**SPEC, "body": {}}})
        assert bad.is_error
