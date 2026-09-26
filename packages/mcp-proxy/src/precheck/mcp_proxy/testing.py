"""In-memory harness: the proxy in front of any MCP server object, with the demo rules, a
fake Jev and an in-memory control plane. Tests pass the upstream (e.g. the lab's mock
tools) so this package never imports it."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from mcp import Client

from precheck.core.agents import AgentProfiles
from precheck.core.engine import EngineRule, rules_from_pack
from precheck.core.schema.loader import load_rule_pack
from precheck.core.settings import EXAMPLES_DIR
from precheck.core.testing import FakeJev, noul
from precheck.mcp_proxy.control import MemoryControlPlane
from precheck.mcp_proxy.policy_source import StaticPolicySource
from precheck.mcp_proxy.server import ProxyServer


def demo_rules() -> list[EngineRule]:
    return rules_from_pack(load_rule_pack(EXAMPLES_DIR / "rulepacks" / "demo.yaml"))


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
    tools_log: Any  # the upstream's call log: `.records` with `.tool` and `.args`
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
        return await client.call_tool(tool, args, meta=cast(Any, meta))

    def reached(self, tool: str) -> list[dict[str, Any]]:
        return [r.args for r in self.tools_log.records if r.tool == tool]


def build_lab(upstream: Any, tools_log: Any, *, rules: list[EngineRule] | None = None) -> Lab:
    jev = FakeJev(answers=dict(SAFE))
    control = MemoryControlPlane()
    policy = StaticPolicySource(list(rules if rules is not None else demo_rules()))
    factory: Callable[[str], Any] = lambda session: upstream  # noqa: E731
    proxy = ProxyServer(
        upstream=factory,
        policy=policy,
        control=control,
        jev=jev,
        agents=AgentProfiles.load(EXAMPLES_DIR / "agents.yaml", default="support-bot"),
        poll_s=0.05,
    )
    return Lab(proxy=proxy, tools_log=tools_log, control=control, policy=policy, jev=jev)
