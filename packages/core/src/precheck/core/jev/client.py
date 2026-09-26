"""Async client for Jev (POST /v1/systemone) with retries, deadline and record/replay."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, Self

import httpx
from pydantic import SecretStr, ValidationError

from precheck.core.jev.errors import (
    JevAuthError,
    JevError,
    JevTimeout,
    JevUnavailable,
    JevValidationError,
)
from precheck.core.jev.fixtures import FixtureStore
from precheck.core.jev.models import JevRequest, JevResponse
from precheck.core.schema import JevQuestion, JevUsage, NoulQuestion

if TYPE_CHECKING:
    from precheck.core.settings import JevSettings

log = logging.getLogger("precheck.core.jev")

JevMode = Literal["live", "record", "replay"]
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504, 529})


class JevClient:
    """One instance per process is fine; it owns a pooled httpx.AsyncClient.

    `deadline_s` bounds a whole `evaluate` call including retries. Backoff is exponential
    with full jitter, never sleeping past the deadline.
    """

    def __init__(
        self,
        api_key: SecretStr | str | None,
        *,
        base_url: str = "https://api.typesafe.ai",
        deadline_s: float = 5.0,
        max_retries: int = 4,
        backoff_base_s: float = 0.2,
        mode: JevMode = "live",
        fixtures: FixtureStore | None = None,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if isinstance(api_key, str):
            api_key = SecretStr(api_key)
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.deadline_s = deadline_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.mode: JevMode = mode
        if mode != "live" and fixtures is None:
            raise ValueError(f"JEV_MODE={mode} needs a fixture directory")
        self.fixtures = fixtures
        self._http = http
        self._owns_http = http is None
        self._sleep = sleep
        self._resolved: dict[str, str] = {}

    def __repr__(self) -> str:  # never show the key
        return f"JevClient(base_url={self.base_url!r}, mode={self.mode!r}, key=***)"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None and self._owns_http:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient()
        return self._http

    # --- public API ---------------------------------------------------------------------

    async def evaluate(
        self, state: Any, questions: dict[str, JevQuestion], model: str = "jev-latest"
    ) -> JevResponse:
        req = JevRequest(model=model, state=state, questions=questions)
        wire = req.wire()
        if self.mode == "replay":
            assert self.fixtures is not None
            return self._parse(self.fixtures.load(wire), latency_ms=0.0, from_fixture=True)
        body, latency_ms, request_id = await self._post_with_retries(wire)
        if self.mode == "record":
            assert self.fixtures is not None
            self.fixtures.save(wire, body)
        return self._parse(body, latency_ms=latency_ms, request_id=request_id)

    async def resolve_model(self, model: str = "jev-latest") -> str:
        """The concrete version (jev-X.Y.Z) that `model` currently points at."""
        if model not in self._resolved:
            probe = {"ok": NoulQuestion(type="noul", instructions="Is this a greeting?")}
            resp = await self.evaluate("hello", probe, model)  # type: ignore[arg-type]
            self._resolved[model] = resp.resolved_model
        return self._resolved[model]

    # --- internals ----------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if self._api_key is None or not self._api_key.get_secret_value():
            raise JevAuthError("TYPESAFE_API_KEY is not configured")
        return {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}

    def _backoff(self, attempt: int) -> float:
        return random.uniform(0, self.backoff_base_s * (2**attempt))

    async def _post_with_retries(
        self, wire: dict[str, Any]
    ) -> tuple[dict[str, Any], float, str | None]:
        url = f"{self.base_url}/v1/systemone"
        headers = self._headers()
        start = time.monotonic()
        deadline = start + self.deadline_s
        last: str = "no attempt made"
        for attempt in range(self.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                resp = await self.http.post(url, json=wire, headers=headers, timeout=remaining)
            except httpx.TimeoutException:
                last = "timeout"
            except httpx.TransportError as e:
                last = f"transport error: {type(e).__name__}"
            else:
                request_id = resp.headers.get("x-typesafe-request-id")
                log.debug(
                    "jev status=%s attempt=%d request_id=%s questions=%d",
                    resp.status_code,
                    attempt,
                    request_id,
                    len(wire.get("questions", {})),
                )
                if resp.status_code == 200:
                    latency_ms = (time.monotonic() - start) * 1000
                    try:
                        return resp.json(), latency_ms, request_id
                    except ValueError as e:
                        raise JevUnavailable("Jev returned invalid JSON") from e
                if resp.status_code in (401, 403):
                    raise JevAuthError(f"Jev rejected the API key (HTTP {resp.status_code})")
                if resp.status_code in (400, 422):
                    raise JevValidationError(resp.status_code, resp.text)
                if resp.status_code not in RETRYABLE_STATUS:
                    raise JevUnavailable(f"unexpected HTTP {resp.status_code} from Jev")
                last = f"HTTP {resp.status_code}"
            if attempt == self.max_retries:
                break
            pause = min(self._backoff(attempt), max(0.0, deadline - time.monotonic()))
            log.debug("jev retrying after %s in %.3fs", last, pause)
            await self._sleep(pause)
        if time.monotonic() >= deadline:
            raise JevTimeout(f"Jev deadline of {self.deadline_s}s exceeded (last: {last})")
        raise JevUnavailable(f"Jev unavailable after {self.max_retries + 1} attempts ({last})")

    def _parse(
        self,
        body: dict[str, Any],
        *,
        latency_ms: float,
        request_id: str | None = None,
        from_fixture: bool = False,
    ) -> JevResponse:
        try:
            return JevResponse(
                resolved_model=body["model"],
                answers=body["answers"],
                usage=JevUsage.model_validate(body.get("usage") or {}),
                latency_ms=latency_ms,
                request_id=request_id,
                from_fixture=from_fixture,
            )
        except (KeyError, TypeError, ValidationError) as e:
            raise JevError(f"unexpected Jev response shape: {e}") from e


def make_jev_client(settings: "JevSettings", **overrides: Any) -> JevClient:
    """Build a client from settings (mode, fixtures dir, deadline, key)."""
    kwargs: dict[str, Any] = {
        "base_url": settings.jev_base_url,
        "deadline_s": settings.jev_deadline_s,
        "mode": settings.jev_mode,
        "fixtures": FixtureStore(settings.jev_fixtures_dir),
    }
    kwargs.update(overrides)
    return JevClient(settings.typesafe_api_key, **kwargs)
