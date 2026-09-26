"""Where an adapter gets its rules. HTTP source: fetch the live policy at start, refresh in
the background, keep the last good copy if the control plane is down. `loaded` stays False
until one fetch succeeds — adapters must fail closed until then."""

import asyncio
import logging
from typing import Protocol

import httpx

from precheck.core.engine import EngineRule
from precheck.core.schema.lab import LivePolicy

log = logging.getLogger("precheck.mcp_proxy.policy")


class PolicySource(Protocol):
    @property
    def loaded(self) -> bool: ...

    @property
    def rules(self) -> list[EngineRule]: ...

    @property
    def version(self) -> int | None: ...

    async def refresh(self) -> bool: ...


def to_engine_rules(policy: LivePolicy) -> list[EngineRule]:
    return [
        EngineRule(id=r.id, gate=r.gate, body=r.body, version=r.version, name=r.name)
        for r in policy.rules
    ]


class StaticPolicySource:
    """Fixed rules (tests, embedding)."""

    def __init__(self, rules: list[EngineRule] | None = None, version: int | None = 1) -> None:
        self._rules = rules
        self._version = version

    @property
    def loaded(self) -> bool:
        return self._rules is not None

    @property
    def rules(self) -> list[EngineRule]:
        return self._rules or []

    @property
    def version(self) -> int | None:
        return self._version

    def set(self, rules: list[EngineRule] | None, version: int | None = None) -> None:
        self._rules, self._version = rules, version

    async def refresh(self) -> bool:
        return self.loaded


class HttpPolicySource:
    def __init__(
        self, api_url: str, *, refresh_s: float = 5.0, http: httpx.AsyncClient | None = None
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.refresh_s = refresh_s
        self._http = http or httpx.AsyncClient(timeout=5.0)
        self._rules: list[EngineRule] | None = None
        self._version: int | None = None
        self.last_error: str | None = None

    @property
    def loaded(self) -> bool:
        return self._rules is not None

    @property
    def rules(self) -> list[EngineRule]:
        return self._rules or []

    @property
    def version(self) -> int | None:
        return self._version

    async def refresh(self) -> bool:
        try:
            resp = await self._http.get(f"{self.api_url}/api/lab/live-policy")
            resp.raise_for_status()
            policy = LivePolicy.model_validate(resp.json())
        except (httpx.HTTPError, ValueError) as e:
            self.last_error = f"{type(e).__name__}: {e}"
            log.warning(
                "policy refresh failed (keeping last good: %s): %s", self.loaded, self.last_error
            )
            return False
        self._rules, self._version, self.last_error = (
            to_engine_rules(policy),
            policy.policy_version,
            None,
        )
        return True

    async def run(self) -> None:
        """Refresh forever (cancel to stop)."""
        while True:
            await self.refresh()
            await asyncio.sleep(self.refresh_s)
