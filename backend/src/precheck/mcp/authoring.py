"""precheck-authoring: an MCP server that lets agents discover, translate, test and
PROPOSE rules. It has no publish/live/status tool on purpose — agents cannot loosen
their own guardrails; a human publishes (considerations.md §9).

Every tool calls the same service layer as the HTTP API; no logic lives here.

    python -m precheck.mcp.authoring --transport http --port 8001   # /mcp, /health
    python -m precheck.mcp.authoring --transport stdio
"""

import argparse
import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from precheck import __version__
from precheck.authoring.dto import RuleCreate, RuleDetail, RuleSummary, RuleUpdate
from precheck.authoring.errors import ConflictError, ServiceError
from precheck.authoring.evaluation import EvaluateResponse, EvaluateScope, load_scope, store_run
from precheck.authoring.rules import RuleService
from precheck.authoring.test_cases import TestCaseCreate, TestCaseService
from precheck.authoring.test_runs import TestRun, TestRunRequest, run_tests
from precheck.authoring.translation import (
    TranslateResponse,
    create_case,
    existing_rules,
    load_case_input,
    update_case,
)
from precheck.config import get_settings
from precheck.db.engine import engine_for, session_factory, session_scope
from precheck.engine import JevEvaluator, evaluate
from precheck.jev import make_jev_client
from precheck.schema import CheckRequest, Gate, RuleSpec
from precheck.translator.llm import JsonLLM, LLMError, make_claude_client
from precheck.translator.pipeline import TranslateInput, Translator

CHECK_REQUEST_DOC = """\
A check request is the event rules judge:
  {"gate": "tool_call" | "egress" | "ingress",
   "agent": {"id": "support-bot", "purpose": "Handles customer support"},
   "context": {"user_goal": "Refund order #1234"},
   "history": [{"tool": "lookup_order", "args": {"order_id": "1234"},
                "result_summary": "Order $620, paid with Visa 4242"}],
   "request": {"kind": "tool_call", "tool": "issue_refund",
               "args": {"order_id": "1234", "amount": 620, "destination": "Mastercard 9911"}},
   "reason": "Customer asked for a refund to a new card"}
Only gate and request are required. request.kind may also be "external_call"
({method, url, body}) or "content" ({text})."""


_ANTICIPATED = (ServiceError, LLMError, ValidationError)


def anticipated[F: Callable[..., Any]](func: F) -> F:
    """Report expected failures (not found, conflicts, validation, LLM errors) to the agent
    with their message; anything else stays a generic crash (details only in server logs)."""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except _ANTICIPATED as e:
                raise ToolError(str(e)) from e

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except _ANTICIPATED as e:
            raise ToolError(str(e)) from e

    return wrapper  # type: ignore[return-value]


@dataclass
class Deps:
    db: sessionmaker[Session]
    jev: JevEvaluator
    llm: JsonLLM


def default_deps() -> Deps:
    settings = get_settings()
    return Deps(
        db=session_factory(engine_for(str(settings.db_path))),
        jev=make_jev_client(settings),
        llm=make_claude_client(settings),
    )


class ProposalResult(BaseModel):
    rule_id: str
    version: int
    created_new_rule: bool
    status: str
    tests_created: int
    note: str


def build_server(deps: Deps) -> MCPServer:
    server = MCPServer(
        name="precheck-authoring",
        version=__version__,
        instructions=(
            "Manage pre-check rules for AI agents: list and read rules, translate plain-language "
            "business cases into draft rules, evaluate check requests, run golden-set tests, and "
            "propose rules or rule changes as drafts. Publishing (making rules live) is a "
            "human-only action in the precheck web app.\n\n" + CHECK_REQUEST_DOC
        ),
    )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def health(_: Request) -> Response:
        return JSONResponse(
            {"status": "ok", "server": "precheck-authoring", "version": __version__}
        )

    @server.tool()
    @anticipated
    def list_rules(
        status: Literal["draft", "live", "archived", "all"] | None = None,
        gate: Gate | None = None,
        query: str | None = None,
    ) -> list[RuleSummary]:
        """List rules (draft and live by default). Filter by status, gate or a search query
        over name, id and source text."""
        with session_scope(deps.db) as s:
            return RuleService(s).list_rules(gate=gate, status=status, q=query)

    @server.tool()
    @anticipated
    def get_rule(rule_id: str) -> RuleDetail:
        """A rule with its current (draft) and live versions: selector, required fields,
        deterministic predicate, Jev questions + thresholds, provenance and version list."""
        with session_scope(deps.db) as s:
            return RuleService(s).get(rule_id)

    @server.tool()
    @anticipated
    async def translate_business_case(
        text: str,
        gate_hint: Gate | None = None,
        tools: list[str] | None = None,
        agent_purpose: str | None = None,
        domains: list[str] | None = None,
    ) -> TranslateResponse:
        """Translate a business rule written in plain language (e.g. "Refunds over $500 need a
        manager. Never refund to a different card.") into draft rule specs with generated
        tests. Nothing is saved as a rule: review the result, then call propose_rule_change
        with a rule's `spec` (include `tests` to save them). If status is
        needs_clarification, answer with answer_clarifications. Uses an LLM (costs money)."""
        inp = TranslateInput(
            text=text,
            gate_hint=gate_hint,
            tools=tools or [],
            agent_purpose=agent_purpose,
            domains=domains or [],
        )
        with session_scope(deps.db) as s:
            existing = existing_rules(s)
        result = await Translator(deps.llm, existing=existing).translate(inp)
        with session_scope(deps.db) as s:
            case_id = create_case(s, inp, result, created_by="agent")
        return TranslateResponse(business_case_id=case_id, result=result)

    @server.tool()
    @anticipated
    async def answer_clarifications(
        business_case_id: str, answers: dict[str, str]
    ) -> TranslateResponse:
        """Re-run a translation with answers to its clarification questions
        ({clarification_id: answer})."""
        with session_scope(deps.db) as s:
            inp = load_case_input(s, business_case_id)
            existing = existing_rules(s)
        inp = inp.model_copy(update={"answers": {**inp.answers, **answers}})
        result = await Translator(deps.llm, existing=existing).translate(inp)
        with session_scope(deps.db) as s:
            update_case(s, business_case_id, inp, result)
        return TranslateResponse(business_case_id=business_case_id, result=result)

    @server.tool(
        description="Evaluate one check request and explain the decision.\n\n"
        + CHECK_REQUEST_DOC
        + """

scope: "live" (published rules, what enforcement runs; default), "draft" (latest versions,
to preview unpublished changes). rule_ids: evaluate only these rules (latest versions)."""
    )
    @anticipated
    async def evaluate_request(
        check_request: CheckRequest,
        scope: Literal["live", "draft"] = "live",
        rule_ids: list[str] | None = None,
    ) -> EvaluateResponse:
        sc = (
            EvaluateScope(kind="rules", rule_ids=rule_ids)
            if rule_ids
            else EvaluateScope(kind=scope)
        )
        with session_scope(deps.db) as s:
            engine_rules, infos = load_scope(s, sc)
        decision = await evaluate(engine_rules, check_request, deps.jev)
        with session_scope(deps.db) as s:
            run_id = store_run(s, sc, check_request, decision)
        return EvaluateResponse(run_id=run_id, decision=decision, rules={r.id: r for r in infos})

    @server.tool()
    @anticipated
    async def run_tests(
        rule_id: str | None = None, rule_status: Literal["draft", "live"] = "draft"
    ) -> TestRun:
        """Run a rule's golden set (or every test case when rule_id is omitted) against its
        draft or live version; returns pass/fail per case with Jev values."""
        req = TestRunRequest(
            scope="rule" if rule_id else "policy", rule_id=rule_id, rule_status=rule_status
        )
        return await _run_tests(deps.db, deps.jev, req)

    @server.tool()
    @anticipated
    def propose_rule_change(rule: RuleSpec) -> ProposalResult:
        """Propose a rule as a DRAFT. A new id creates a new rule marked "proposed by agent";
        an existing id adds a new draft version to that rule (a live rule keeps enforcing its
        published version). The spec's `tests` are saved as test cases. A human reviews and
        publishes in the web app — this tool can never make anything live."""
        with session_scope(deps.db) as s:
            svc = RuleService(s)
            existing = svc.repo.get(rule.id)
            if existing is None:
                detail = svc.create(
                    RuleCreate(
                        id=rule.id,
                        name=rule.name,
                        gate=rule.gate,
                        body=rule.body,
                        source_text=rule.source_text,
                        explanation=rule.explanation,
                    ),
                    created_by="agent",
                )
                created = True
            else:
                if existing.status == "archived":
                    raise ConflictError(f"rule {rule.id!r} is archived")
                if existing.gate != rule.gate.value:
                    raise ConflictError(
                        f"rule {rule.id!r} is a {existing.gate} rule; gate can't change"
                    )
                detail = svc.update(
                    rule.id,
                    RuleUpdate(
                        body=rule.body,
                        name=rule.name,
                        source_text=rule.source_text,
                        explanation=rule.explanation,
                    ),
                )
                created = False
            cases = TestCaseService(s)
            for t in rule.tests:
                cases.create(
                    TestCaseCreate(
                        rule_id=detail.id,
                        name=t.name,
                        check_request=t.check_request,
                        expected_verdict=t.expected_verdict,
                        origin="generated",
                    )
                )
            note = (
                "Draft created; a human must review and publish it."
                if created
                else f"New draft version v{detail.current_version}; live stays at "
                f"v{detail.live_version}."
                if detail.live_version
                else f"New draft version v{detail.current_version}."
            )
            return ProposalResult(
                rule_id=detail.id,
                version=detail.current_version,
                created_new_rule=created,
                status=detail.status,
                tests_created=len(rule.tests),
                note=note,
            )

    return server


async def _run_tests(db: sessionmaker[Session], jev: JevEvaluator, req: TestRunRequest) -> TestRun:
    return await run_tests(db, jev, req)


ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*", "authoring-mcp:*"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="precheck authoring MCP server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=get_settings().host)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    server = build_server(default_deps())
    if args.transport == "stdio":
        server.run("stdio")
        return
    server.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        # Explicit DNS-rebinding protection (the SDK only enables it for loopback binds).
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=ALLOWED_HOSTS,
            allowed_origins=[f"http://{h}" for h in ALLOWED_HOSTS],
        ),
    )


if __name__ == "__main__":
    main()
