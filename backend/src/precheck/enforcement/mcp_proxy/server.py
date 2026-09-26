"""Enforcement MCP proxy: agents connect here instead of to their tools.

tools/list  upstream tools, each with an injected required `reason` parameter.
tools/call  strip `reason`, build a CheckRequest (agent profile, user goal, session
            history, request, reason), evaluate the LIVE rules in-process, then:
              allow    -> forward upstream; check the result (ingress gate) before
                          returning it; record it in the session history
              deny     -> tool error explaining the rules; nothing forwarded
              escalate -> tool error with an escalation id; nothing forwarded; once a
                          human approves, the same call (session, tool, args) is allowed once
No policy loaded yet -> every call is denied (fail closed). Decision events and
escalations go to the control plane asynchronously; they never block a call.
"""

import asyncio
import hashlib
import json
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, Tool

from mcp import Client
from precheck import __version__
from precheck.enforcement.agents import AgentProfiles
from precheck.enforcement.control import ControlPlane
from precheck.enforcement.policy_source import PolicySource
from precheck.engine import JevEvaluator, evaluate
from precheck.schema import CheckRequest, Decision, Gate, HistoryItem, Verdict, canonical_json
from precheck.schema.lab import DecisionEvent, EscalationCreate

REASON_PARAM = "reason"
REASON_SCHEMA = {
    "type": "string",
    "description": (
        "Why you are making this call: the user need it serves and why this tool/arguments are "
        "right. Required; checked against policy before the call runs."
    ),
}
META_SESSION = "precheck/session"
META_AGENT = "precheck/agent_id"
META_GOAL = "precheck/user_goal"
SUMMARY_CHARS = 300
WITHHELD = "[result withheld by precheck]"

# What to connect upstream for a given session: an in-process server or a Transport.
UpstreamFactory = Callable[[str], Any]


@dataclass
class SessionState:
    history: deque[HistoryItem] = field(default_factory=lambda: deque(maxlen=20))
    steps: int = 0


def args_hash(args: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(args).encode()).hexdigest()


def result_text(result: CallToolResult) -> str:
    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    if texts:
        return "\n".join(texts)
    if result.structured_content is not None:
        return json.dumps(result.structured_content, sort_keys=True)
    return ""


def explain(decision: Decision, verdict: Verdict) -> str:
    fired = [r for r in decision.rule_results if r.matched and r.verdict is verdict]
    return "; ".join(f"{r.rule_id}: {r.reason}" for r in fired) or "no rule gave a reason"


def error_result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


class ProxyServer(MCPServer):
    def __init__(
        self,
        *,
        upstream: UpstreamFactory,
        policy: PolicySource,
        control: ControlPlane,
        jev: JevEvaluator | None,
        agents: AgentProfiles,
        inject_reason: bool = True,
        log_check_requests: bool = True,
        poll_s: float = 1.0,
        background: list[Callable[[], Any]] | None = None,
        max_sessions: int = 1000,
    ) -> None:
        super().__init__(
            name="precheck-proxy",
            version=__version__,
            instructions="Tools behind a precheck enforcement proxy: every call needs a `reason` "
            "and is checked against policy; blocked calls return an explanation.",
            lifespan=self._lifespan,
        )
        self.upstream = upstream
        self.policy = policy
        self.control = control
        self.jev = jev
        self.agents = agents
        self.inject_reason = inject_reason
        self.log_check_requests = log_check_requests
        self.poll_s = poll_s
        self._background = background or []
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()
        self._max_sessions = max_sessions
        self._pending: dict[
            str, tuple[str, str, str]
        ] = {}  # escalation id -> (session, tool, args hash)
        self._grants: dict[tuple[str, str, str], list[str]] = {}  # key -> approved escalation ids
        self._tools_cache: tuple[float, list[Tool]] | None = None

    # --- lifecycle --------------------------------------------------------------------

    @staticmethod
    @asynccontextmanager
    async def _lifespan(server: MCPServer) -> AsyncIterator[None]:
        assert isinstance(server, ProxyServer)
        tasks = [asyncio.create_task(fn()) for fn in server._background]
        tasks.append(asyncio.create_task(server._poll_approvals_forever()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()

    async def _poll_approvals_forever(self) -> None:
        while True:
            await self.poll_approvals()
            await asyncio.sleep(self.poll_s)

    async def poll_approvals(self) -> None:
        if not self._pending:
            return
        statuses = await self.control.escalation_statuses(list(self._pending))
        for esc_id, status in statuses.items():
            if status == "approved":
                key = self._pending.pop(esc_id)
                self._grants.setdefault(key, []).append(esc_id)
            elif status in ("denied", "consumed"):
                self._pending.pop(esc_id, None)

    # --- upstream -----------------------------------------------------------------------

    async def _upstream_tools(self) -> list[Tool]:
        now = time.monotonic()
        if self._tools_cache and now - self._tools_cache[0] < 30:
            return self._tools_cache[1]
        async with Client(self.upstream("tools-list")) as client:
            tools = list((await client.list_tools()).tools)
        self._tools_cache = (now, tools)
        return tools

    async def _forward(self, session: str, name: str, args: dict[str, Any]) -> CallToolResult:
        async with Client(self.upstream(session)) as client:
            return await client.call_tool(name, args)

    # --- MCP surface --------------------------------------------------------------------

    async def list_tools(self) -> list[Tool]:
        tools = await self._upstream_tools()
        if not self.inject_reason:
            return tools
        out = []
        for t in tools:
            schema = json.loads(json.dumps(t.input_schema))
            schema.setdefault("properties", {})[REASON_PARAM] = REASON_SCHEMA
            required = [r for r in schema.get("required", []) if r != REASON_PARAM]
            schema["required"] = [*required, REASON_PARAM]
            out.append(t.model_copy(update={"input_schema": schema}))
        return out

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Context[Any, Any] | None = None
    ) -> CallToolResult:
        started = time.perf_counter()
        meta, headers = self._meta_and_headers(context)
        session_id = str(
            meta.get(META_SESSION)
            or headers.get("x-precheck-session")
            or headers.get("mcp-session-id")
            or "default"
        )
        state = self._session(session_id)
        state.steps += 1
        step = state.steps
        args = dict(arguments)
        reason = args.pop(REASON_PARAM, None) if self.inject_reason else None
        agent = self.agents.resolve(meta.get(META_AGENT) or headers.get("x-agent-id"))
        goal = meta.get(META_GOAL) or headers.get("x-user-goal")
        base: dict[str, Any] = {
            "agent": agent,
            "context": {"user_goal": goal} if goal else None,
            "history": list(state.history) or None,
            "reason": reason if isinstance(reason, str) and reason.strip() else None,
        }
        cr = CheckRequest.model_validate(
            {
                "gate": Gate.tool_call,
                "request": {"kind": "tool_call", "tool": name, "args": args},
                **base,
            }
        )
        key = (session_id, name, args_hash(args))

        def log(
            gate: Gate,
            verdict: Verdict,
            forwarded: bool,
            decision: Decision | None,
            request: CheckRequest,
            note: str | None = None,
            escalation_id: str | None = None,
            step_no: int = step,
        ) -> None:
            self.control.log_decision(
                DecisionEvent(
                    id=str(uuid.uuid4()),
                    session=session_id,
                    step=step_no,
                    gate=gate,
                    tool=name,
                    verdict=verdict,
                    forwarded=forwarded,
                    escalation_id=escalation_id,
                    note=note,
                    check_request=request if self.log_check_requests else None,
                    decision=decision,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )

        # 1. A human-approved escalation lets exactly this call through once.
        if self._grants.get(key):
            esc_id = self._grants[key].pop(0)
            self.control.consume_escalation(esc_id)
            log(
                Gate.tool_call,
                Verdict.allow,
                True,
                None,
                cr,
                note="escalation approved; grant used",
                escalation_id=esc_id,
            )
        # 2. Fail closed until a policy has been loaded.
        elif not self.policy.loaded:
            log(Gate.tool_call, Verdict.deny, False, None, cr, note="no policy loaded")
            return error_result(
                "Blocked by precheck: no policy loaded (the enforcement proxy fails closed)."
            )
        else:
            decision = await evaluate(self.policy.rules, cr, self.jev)
            if decision.verdict is Verdict.deny:
                log(Gate.tool_call, Verdict.deny, False, decision, cr)
                return error_result(
                    f"Blocked by precheck (deny): {explain(decision, Verdict.deny)}"
                )
            if decision.verdict is Verdict.escalate:
                esc_id = str(uuid.uuid4())
                self._pending[esc_id] = key
                self.control.create_escalation(
                    EscalationCreate(
                        id=esc_id,
                        session=session_id,
                        tool=name,
                        args_hash=key[2],
                        check_request=cr,
                        decision=decision,
                    )
                )
                log(Gate.tool_call, Verdict.escalate, False, decision, cr, escalation_id=esc_id)
                why = explain(decision, Verdict.escalate)
                return error_result(
                    f"Held for human approval (escalation {esc_id}): {why}. Tell the user it needs "
                    "approval; the same call can be retried once it is approved."
                )
            log(Gate.tool_call, Verdict.allow, True, decision, cr)

        # 3. Forward, then check the result before the agent sees it (ingress gate).
        result = await self._forward(session_id, name, args)
        text = result_text(result)
        if result.is_error or not self.policy.loaded:
            state.history.append(
                HistoryItem(tool=name, args=args, result_summary=text[:SUMMARY_CHARS])
            )
            return result
        result_cr = CheckRequest.model_validate(
            {
                "gate": Gate.ingress,
                "request": {"kind": "content", "tool": name, "text": text or "(empty)"},
                **base,
            }
        )
        d2 = await evaluate(self.policy.rules, result_cr, self.jev)
        if d2.verdict is not Verdict.allow:
            state.history.append(HistoryItem(tool=name, args=args, result_summary=WITHHELD))
            log(Gate.ingress, d2.verdict, False, d2, result_cr)
            why = explain(d2, d2.verdict)
            return error_result(
                f"The result of {name} was withheld by precheck ({d2.verdict.value}): {why}"
            )
        if not d2.gate_default_applied:
            log(Gate.ingress, Verdict.allow, True, d2, result_cr)
        state.history.append(HistoryItem(tool=name, args=args, result_summary=text[:SUMMARY_CHARS]))
        return result

    # --- helpers ------------------------------------------------------------------------

    def _session(self, session_id: str) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            state = self._sessions[session_id] = SessionState()
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return state

    def history(self, session_id: str) -> list[HistoryItem]:
        state = self._sessions.get(session_id)
        return list(state.history) if state else []

    @staticmethod
    def _meta_and_headers(
        context: Context[Any, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if context is None:
            return {}, {}
        try:
            meta = dict(context.request_context.meta or {})
        except (AttributeError, LookupError, ValueError):
            meta = {}
        try:
            headers = {k.lower(): v for k, v in (context.headers or {}).items()}
        except (AttributeError, LookupError):
            headers = {}
        return meta, headers
