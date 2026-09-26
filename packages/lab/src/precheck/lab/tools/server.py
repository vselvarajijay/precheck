"""Mock tools MCP server: realistic business tools with in-memory data and a call log.

Nothing leaves the process: `http_request` records what it WOULD have sent. Every call is
logged (with the caller's session) so tests can prove a blocked call never reached a tool.

    python -m precheck.lab.tools.server --port 8100
    GET /calls?session=ID   POST /reset   GET /health
"""

import argparse
import itertools
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from precheck.core import __version__
from precheck.lab.tools.data import CUSTOMERS, ORDERS, PAGES

SESSION_HEADER = "x-precheck-session"


class CallRecord(BaseModel):
    seq: int
    session: str
    tool: str
    args: dict[str, Any]
    at: float


@dataclass
class CallLog:
    records: list[CallRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _seq: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def add(self, session: str, tool: str, args: dict[str, Any]) -> None:
        with self._lock:
            self.records.append(
                CallRecord(
                    seq=next(self._seq), session=session, tool=tool, args=args, at=time.time()
                )
            )

    def for_session(self, session: str | None) -> list[CallRecord]:
        with self._lock:
            return [r for r in self.records if session is None or r.session == session]

    def clear(self) -> None:
        with self._lock:
            self.records.clear()


def _session(ctx: Context | None) -> str:
    headers = ctx.headers if ctx is not None else None
    if not headers:
        return "local"
    return headers.get(SESSION_HEADER) or headers.get("mcp-session-id") or "local"


def build_server(log: CallLog | None = None) -> tuple[MCPServer, CallLog]:
    log = log or CallLog()
    server = MCPServer(
        name="precheck-lab-tools",
        version=__version__,
        instructions="Mock support tools for a demo shop: orders, refunds, customers, web.",
    )

    def record(ctx: Context | None, tool: str, args: dict[str, Any]) -> None:
        log.add(_session(ctx), tool, args)

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "server": "precheck-lab-tools"})

    @server.custom_route("/calls", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def calls(request: Request) -> Response:
        records = log.for_session(request.query_params.get("session"))
        return JSONResponse([r.model_dump() for r in records])

    @server.custom_route("/reset", methods=["POST"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def reset(_: Request) -> Response:
        log.clear()
        return JSONResponse({"status": "reset"})

    @server.tool()
    def lookup_order(order_id: str, ctx: Context) -> dict[str, Any]:
        """Look up an order: amount, currency, payment method, status and items."""
        record(ctx, "lookup_order", {"order_id": order_id})
        if order_id not in ORDERS:
            raise ToolError(f"order {order_id} not found")
        return dict(ORDERS[order_id])

    @server.tool()
    def read_customer_profile(customer_id: str, ctx: Context) -> dict[str, Any]:
        """Read a customer's profile: name, email, phone and address (personal data)."""
        record(ctx, "read_customer_profile", {"customer_id": customer_id})
        if customer_id not in CUSTOMERS:
            raise ToolError(f"customer {customer_id} not found")
        return dict(CUSTOMERS[customer_id])

    @server.tool()
    def issue_refund(
        order_id: str, amount: float, destination: str, ctx: Context
    ) -> dict[str, Any]:
        """Refund money for an order to a card or account (destination)."""
        record(
            ctx,
            "issue_refund",
            {"order_id": order_id, "amount": amount, "destination": destination},
        )
        return {
            "refund_id": f"rf_{order_id}_{int(amount * 100)}",
            "status": "issued",
            "amount": amount,
            "destination": destination,
        }

    @server.tool()
    def send_email(to: str, subject: str, body: str, ctx: Context) -> dict[str, Any]:
        """Send an email to a customer or colleague."""
        record(ctx, "send_email", {"to": to, "subject": subject, "body": body})
        return {"message_id": f"msg_{len(log.records)}", "status": "queued", "to": to}

    @server.tool()
    def http_request(
        method: str, url: str, ctx: Context, body: str | None = None
    ) -> dict[str, Any]:
        """Make an outbound HTTP request to an external service (method, url, optional body).
        In this lab nothing is sent; the would-be request is recorded."""
        record(ctx, "http_request", {"method": method, "url": url, "body": body})
        return {"status": 200, "recorded": True, "note": "lab: request recorded, not sent"}

    @server.tool()
    def fetch_web_page(url: str, ctx: Context) -> dict[str, Any]:
        """Fetch a web page and return its text."""
        record(ctx, "fetch_web_page", {"url": url})
        if url not in PAGES:
            return {"url": url, "status": 404, "text": "Not found"}
        return {"url": url, "status": 200, "text": PAGES[url]}

    @server.tool()
    def delete_customer(customer_id: str, ctx: Context) -> dict[str, Any]:
        """Permanently delete a customer account and its data (irreversible)."""
        record(ctx, "delete_customer", {"customer_id": customer_id})
        return {"customer_id": customer_id, "deleted": True}

    @server.tool()
    def run_shell(command: str, ctx: Context) -> dict[str, Any]:
        """Run a shell command on the support server."""
        record(ctx, "run_shell", {"command": command})
        return {"exit_code": 0, "stdout": "(lab) command not executed"}

    return server, log


ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*", "tools:*", "tools-e2e:*"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="precheck mock tools MCP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args(argv)
    server, _ = build_server()
    server.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=ALLOWED_HOSTS,
            allowed_origins=[f"http://{h}" for h in ALLOWED_HOSTS],
        ),
    )


if __name__ == "__main__":
    main()
