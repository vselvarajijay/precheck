"""Run the enforcement proxy: `python -m precheck.enforcement.mcp_proxy --port 8200`."""

import argparse
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from precheck.config import get_settings
from precheck.enforcement.agents import AgentProfiles
from precheck.enforcement.control import HttpControlPlane
from precheck.enforcement.mcp_proxy.server import ProxyServer
from precheck.enforcement.policy_source import HttpPolicySource
from precheck.jev import make_jev_client

ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*", "proxy:*", "proxy-e2e:*"]


def http_upstream(url: str) -> Any:
    """Upstream factory: a streamable-HTTP connection tagged with the agent's session."""

    def factory(session: str) -> Any:
        @asynccontextmanager
        async def transport() -> AsyncIterator[Any]:
            timeout = httpx2.Timeout(30.0, read=120.0)
            async with (
                httpx2.AsyncClient(
                    headers={"x-precheck-session": session}, timeout=timeout
                ) as http,
                streamable_http_client(url, http_client=http) as streams,
            ):
                yield streams

        return transport()

    return factory


def build(settings: Any = None) -> ProxyServer:
    settings = settings or get_settings()
    policy = HttpPolicySource(settings.api_url, refresh_s=settings.proxy_refresh_s)
    control = HttpControlPlane(settings.api_url)
    server = ProxyServer(
        upstream=http_upstream(settings.proxy_upstream_url),
        policy=policy,
        control=control,
        jev=make_jev_client(settings),
        agents=AgentProfiles.load(settings.proxy_agents_file, default=settings.proxy_default_agent),
        inject_reason=settings.proxy_inject_reason,
        log_check_requests=settings.proxy_log_check_requests,
        background=[policy.run, control.run],
    )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def health(_: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok",
                "server": "precheck-proxy",
                "policy_loaded": policy.loaded,
                "policy_version": policy.version,
                "rules": len(policy.rules),
                "last_error": policy.last_error,
                "reports_dropped": control.dropped,
            }
        )

    @server.custom_route("/reload", methods=["POST"], include_in_schema=False)  # type: ignore[untyped-decorator]
    async def reload(_: Request) -> Response:
        ok = await policy.refresh()
        return JSONResponse(
            {"reloaded": ok, "policy_version": policy.version, "rules": len(policy.rules)},
            status_code=200 if ok else 503,
        )

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="precheck enforcement MCP proxy")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8200)
    args = parser.parse_args(argv)
    build().run(
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
