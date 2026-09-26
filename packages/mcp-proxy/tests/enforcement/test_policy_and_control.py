import asyncio

import httpx
import pytest

from precheck.core.schema.lab import DecisionEvent
from precheck.mcp_proxy.control import HttpControlPlane
from precheck.mcp_proxy.policy_source import HttpPolicySource

POLICY = {
    "policy_version": 3,
    "content_hash": "sha256:x",
    "rules": [
        {
            "id": "limit",
            "name": "Limit",
            "gate": "tool_call",
            "version": 2,
            "body": {
                "deterministic": {
                    "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
                    "verdict_when_true": "escalate",
                }
            },
        }
    ],
}


def transport(state: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if state.get("down"):
            raise httpx.ConnectError("api down")
        state.setdefault("requests", []).append((request.method, request.url.path))
        if request.url.path == "/api/lab/live-policy":
            return httpx.Response(200, json=state.get("policy", POLICY))
        if request.url.path == "/api/lab/escalations":
            return httpx.Response(200, json=[{"id": "e1", "status": "approved"}])
        return httpx.Response(204)

    return httpx.MockTransport(handler)


async def test_policy_refresh_keeps_last_good_when_api_down() -> None:
    state: dict = {}
    src = HttpPolicySource("http://api", http=httpx.AsyncClient(transport=transport(state)))
    assert not src.loaded and src.rules == []
    assert (
        await src.refresh()
        and src.loaded
        and src.version == 3
        and [r.id for r in src.rules] == ["limit"]
    )
    state["down"] = True
    assert not await src.refresh()
    assert (
        src.loaded
        and [r.id for r in src.rules] == ["limit"]
        and "api down" in (src.last_error or "")
    )
    state["down"] = False
    state["policy"] = {**POLICY, "policy_version": 4, "rules": []}
    assert await src.refresh() and src.version == 4 and src.rules == []


async def test_cold_start_api_down_stays_unloaded() -> None:
    src = HttpPolicySource(
        "http://api", http=httpx.AsyncClient(transport=transport({"down": True}))
    )
    assert not await src.refresh() and not src.loaded


async def test_decision_log_failure_never_blocks() -> None:
    cp = HttpControlPlane("http://api", http=httpx.AsyncClient(transport=transport({"down": True})))
    event = DecisionEvent(
        id="d1", session="s", step=1, gate="tool_call", verdict="allow", forwarded=True
    )
    cp.log_decision(event)  # returns immediately
    worker = asyncio.create_task(cp.run())
    await asyncio.sleep(1.5)
    worker.cancel()
    assert cp.dropped == 1


async def test_control_plane_sends_and_polls() -> None:
    state: dict = {}
    cp = HttpControlPlane("http://api", http=httpx.AsyncClient(transport=transport(state)))
    cp.log_decision(
        DecisionEvent(
            id="d1", session="s", step=1, gate="tool_call", verdict="deny", forwarded=False
        )
    )
    cp.consume_escalation("e1")
    worker = asyncio.create_task(cp.run())
    await cp.drain()
    worker.cancel()
    assert ("POST", "/api/lab/decisions") in state["requests"]
    assert ("POST", "/api/lab/escalations/e1/consume") in state["requests"]
    assert await cp.escalation_statuses(["e1"]) == {"e1": "approved"}


@pytest.mark.parametrize("n", [3])
async def test_queue_full_drops_instead_of_blocking(n: int) -> None:
    cp = HttpControlPlane("http://api", max_queue=1)
    for i in range(n):
        cp.log_decision(
            DecisionEvent(
                id=f"d{i}", session="s", step=i, gate="tool_call", verdict="allow", forwarded=True
            )
        )
    assert cp.dropped == n - 1
