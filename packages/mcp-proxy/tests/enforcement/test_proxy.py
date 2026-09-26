import asyncio

from mcp import Client

from precheck.core.engine import rules_from_pack
from precheck.core.schema import RulePack
from precheck.core.testing import noul

from .conftest import Lab

REFUND_OK = {
    "order_id": "1234",
    "amount": 120,
    "destination": "Visa ending 4242",
    "reason": "Customer returned the sweater; refunding the original Visa",
}


async def test_reason_injected_and_stripped_upstream(lab: Lab) -> None:
    async with Client(lab.proxy) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert len(tools) == 8
        for t in tools.values():
            assert t.input_schema["required"][-1] == "reason"
            assert t.input_schema["properties"]["reason"]["type"] == "string"
        # The card rule needs history (how the order was paid), so look it up first.
        await lab.call(c, "lookup_order", {"order_id": "1234", "reason": "check how it was paid"})
        res = await lab.call(c, "issue_refund", REFUND_OK)
    assert not res.is_error, res.content
    assert lab.reached("issue_refund") == [
        {"order_id": "1234", "amount": 120.0, "destination": "Visa ending 4242"}
    ]
    event = next(e for e in lab.control.decisions if e.tool == "issue_refund")
    assert event.check_request.reason.startswith("Customer returned")  # type: ignore[union-attr]
    assert event.check_request.agent.purpose.startswith("Handles customer support")  # type: ignore[union-attr]
    assert event.check_request.context.user_goal == "help the customer"  # type: ignore[union-attr]


async def test_proxy_not_forwarded_deny_and_escalate(lab: Lab) -> None:
    async with Client(lab.proxy) as c:
        shell = await lab.call(
            c, "run_shell", {"command": "ls", "reason": "check the disk space quickly"}
        )
        big = await lab.call(c, "issue_refund", {**REFUND_OK, "amount": 900})
        no_reason = await lab.call(c, "delete_customer", {"customer_id": "c_42"})
    assert shell.is_error and "Blocked by precheck (deny)" in shell.content[0].text
    assert "support-tools-only" in shell.content[0].text
    assert big.is_error and "Held for human approval" in big.content[0].text
    assert no_reason.is_error and "reason-required" in no_reason.content[0].text
    assert lab.tools_log.records == []  # nothing blocked reached a tool
    verdicts = [(e.tool, e.verdict.value, e.forwarded) for e in lab.control.decisions]
    assert verdicts == [
        ("run_shell", "deny", False),
        ("issue_refund", "escalate", False),
        ("delete_customer", "deny", False),
    ]


async def test_history_accumulates_per_session_and_truncates(lab: Lab) -> None:
    async with Client(lab.proxy) as c:
        await lab.call(
            c, "lookup_order", {"order_id": "1234", "reason": "check the order"}, session="a"
        )
        await lab.call(
            c,
            "read_customer_profile",
            {"customer_id": "c_88", "reason": "check the address"},
            session="a",
        )
        await lab.call(
            c, "lookup_order", {"order_id": "9012", "reason": "check the order"}, session="b"
        )
        await lab.call(
            c,
            "fetch_web_page",
            {"url": "https://help.example-shop.com/returns", "reason": "policy"},
            session="a",
        )
    a, b = lab.proxy.history("a"), lab.proxy.history("b")
    assert [h.tool for h in a] == ["lookup_order", "read_customer_profile", "fetch_web_page"]
    assert [h.tool for h in b] == ["lookup_order"]
    assert "Visa ending 4242" in (a[0].result_summary or "") and a[0].args == {"order_id": "1234"}
    assert all(len(h.result_summary or "") <= 300 for h in a)
    # The history reached the rules: the second call's check request carries the first call.
    second = [e for e in lab.control.decisions if e.session == "a" and e.gate.value == "tool_call"][
        1
    ]
    assert [h.tool for h in second.check_request.history] == ["lookup_order"]  # type: ignore[union-attr]


async def test_response_gate_blocks_injection_page(lab: Lab) -> None:
    lab.jev.answers["injection"] = noul(0.97)
    async with Client(lab.proxy) as c:
        res = await lab.call(
            c,
            "fetch_web_page",
            {
                "url": "https://reviews.example.org/espresso-machine",
                "reason": "the customer asked about reviews",
            },
        )
    assert res.is_error and "withheld by precheck" in res.content[0].text
    assert "ignore all previous instructions" not in res.content[0].text
    assert lab.reached("fetch_web_page")  # the call itself was allowed and executed
    gates = [(e.gate.value, e.verdict.value, e.forwarded) for e in lab.control.decisions]
    assert gates == [("tool_call", "allow", True), ("ingress", "deny", False)]
    # Trusted internal results aren't sent to the ingress rule (it only covers fetched pages).
    assert lab.proxy.history("s1")[0].result_summary == "[result withheld by precheck]"


async def test_escalation_approve_allows_retry_once(lab: Lab) -> None:
    big = {**REFUND_OK, "amount": 900}
    async with Client(lab.proxy) as c:
        first = await lab.call(c, "issue_refund", big)
        assert first.is_error and "Held for human approval" in first.content[0].text
        [esc_id] = lab.control.escalations
        lab.control.approve(esc_id)
        await lab.proxy.poll_approvals()
        second = await lab.call(c, "issue_refund", big)
        assert not second.is_error
        third = await lab.call(c, "issue_refund", big)
        assert third.is_error and "Held for human approval" in third.content[0].text
        different = await lab.call(
            c, "issue_refund", {**big, "amount": 901}
        )  # no grant for other args
        assert different.is_error
    assert lab.control.statuses[esc_id] == "consumed"
    assert len(lab.reached("issue_refund")) == 1
    notes = [e.note for e in lab.control.decisions if e.note]
    assert notes == ["escalation approved; grant used"]


async def test_retry_of_pending_escalation_checks_approval_immediately(lab: Lab) -> None:
    """No waiting for the background poll: a retry of the held call asks for its status."""
    big = {**REFUND_OK, "amount": 900}
    async with Client(lab.proxy) as c:
        await lab.call(c, "issue_refund", big)
        [esc_id] = lab.control.escalations
        lab.control.approve(esc_id)
        retry = await lab.call(c, "issue_refund", big)  # no poll_approvals() in between
        assert not retry.is_error
    assert lab.control.statuses[esc_id] == "consumed"


async def test_denied_escalation_never_grants(lab: Lab) -> None:
    big = {**REFUND_OK, "amount": 900}
    async with Client(lab.proxy) as c:
        await lab.call(c, "issue_refund", big)
        [esc_id] = lab.control.escalations
        lab.control.deny(esc_id)
        await lab.proxy.poll_approvals()
        again = await lab.call(c, "issue_refund", big)
    assert again.is_error and lab.reached("issue_refund") == []


async def test_cold_start_without_policy_denies_all(lab: Lab) -> None:
    lab.policy.set(None)
    async with Client(lab.proxy) as c:
        res = await lab.call(c, "lookup_order", {"order_id": "1234", "reason": "check"})
    assert res.is_error and "no policy loaded" in res.content[0].text
    assert lab.tools_log.records == []
    assert lab.control.decisions[0].note == "no policy loaded"


async def test_hot_rule_update_is_used_on_next_call(lab: Lab) -> None:
    async with Client(lab.proxy) as c:
        assert not (
            await lab.call(c, "lookup_order", {"order_id": "1234", "reason": "check"})
        ).is_error
        extra = RulePack.model_validate(
            {
                "schema": 1,
                "rules": [
                    {
                        "id": "no-lookups-today",
                        "name": "No lookups",
                        "gate": "tool_call",
                        "body": {
                            "deterministic": {
                                "predicate": {
                                    "op": "eq",
                                    "path": "request.tool",
                                    "value": "lookup_order",
                                },
                                "verdict_when_true": "deny",
                            }
                        },
                    }
                ],
            }
        )
        lab.policy.set([*lab.policy.rules, *rules_from_pack(extra)], version=2)
        res = await lab.call(c, "lookup_order", {"order_id": "1234", "reason": "check"})
    assert res.is_error and "no-lookups-today" in res.content[0].text


async def test_background_poller_picks_up_approvals(lab: Lab) -> None:
    async with Client(lab.proxy) as c:
        await lab.call(c, "issue_refund", {**REFUND_OK, "amount": 900})
        [esc_id] = lab.control.escalations
        lab.control.approve(esc_id)
        await asyncio.sleep(0.2)  # poller runs every 50 ms in the lifespan
        again = await lab.call(c, "issue_refund", {**REFUND_OK, "amount": 900})
    assert not again.is_error
