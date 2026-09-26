from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from mcp import Client
from precheck.enforcement.agents import AgentProfiles
from precheck.enforcement.control import MemoryControlPlane
from precheck.enforcement.mcp_proxy.server import ProxyServer
from precheck.enforcement.policy_source import StaticPolicySource
from precheck.engine import rules_from_pack
from precheck.labtools.server import CallLog, build_server
from precheck.schema.loader import load_rule_pack

from ..engine.conftest import FakeJev, noul

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DEMO_RULES = rules_from_pack(load_rule_pack(EXAMPLES / "rulepacks" / "demo.yaml"))

# Answers by question id: a "safe" world by default; tests override per case.
SAFE = {
    "different_method": noul(0.03),
    "justified": noul(0.95),
    "manipulation": noul(0.05),
    "carries_pii": noul(0.05),
    "injection": noul(0.02),
}


@dataclass
class Lab:
    proxy: ProxyServer
    tools_log: CallLog
    control: MemoryControlPlane
    policy: StaticPolicySource
    jev: FakeJev

    async def call(
        self,
        client: Client,
        tool: str,
        args: dict[str, Any],
        session: str = "s1",
        goal: str | None = "help the customer",
    ) -> Any:
        meta = {"precheck/session": session, "precheck/agent_id": "support-bot"}
        if goal:
            meta["precheck/user_goal"] = goal
        return await client.call_tool(tool, args, meta=meta)

    def reached(self, tool: str) -> list[dict[str, Any]]:
        return [r.args for r in self.tools_log.records if r.tool == tool]


@pytest.fixture
def lab() -> Lab:
    tools_server, log = build_server()
    jev = FakeJev(answers=dict(SAFE))
    control = MemoryControlPlane()
    policy = StaticPolicySource(list(DEMO_RULES))
    proxy = ProxyServer(
        upstream=lambda session: tools_server,
        policy=policy,
        control=control,
        jev=jev,
        agents=AgentProfiles.load(EXAMPLES / "agents.yaml", default="support-bot"),
        poll_s=0.05,
    )
    return Lab(proxy=proxy, tools_log=log, control=control, policy=policy, jev=jev)
