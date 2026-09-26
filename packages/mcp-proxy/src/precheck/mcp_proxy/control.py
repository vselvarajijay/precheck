"""Reporting to the control plane, off the request path: decision events and escalations
are queued and sent by a background worker (failures never block or fail a call);
approvals are polled in the background."""

import asyncio
import logging
from typing import Protocol

import httpx

from precheck.core.schema.lab import DecisionEvent, EscalationCreate

log = logging.getLogger("precheck.mcp_proxy.control")


class ControlPlane(Protocol):
    def log_decision(self, event: DecisionEvent) -> None: ...

    def create_escalation(self, data: EscalationCreate) -> None: ...

    def consume_escalation(self, escalation_id: str) -> None: ...

    async def escalation_statuses(self, ids: list[str]) -> dict[str, str]: ...


class MemoryControlPlane:
    """In-memory control plane (tests): approve with `approve(id)`."""

    def __init__(self) -> None:
        self.decisions: list[DecisionEvent] = []
        self.escalations: dict[str, EscalationCreate] = {}
        self.statuses: dict[str, str] = {}

    def log_decision(self, event: DecisionEvent) -> None:
        self.decisions.append(event)

    def create_escalation(self, data: EscalationCreate) -> None:
        self.escalations[data.id] = data
        self.statuses[data.id] = "pending"

    def consume_escalation(self, escalation_id: str) -> None:
        self.statuses[escalation_id] = "consumed"

    def approve(self, escalation_id: str) -> None:
        self.statuses[escalation_id] = "approved"

    def deny(self, escalation_id: str) -> None:
        self.statuses[escalation_id] = "denied"

    async def escalation_statuses(self, ids: list[str]) -> dict[str, str]:
        return {i: self.statuses[i] for i in ids if i in self.statuses}


class HttpControlPlane:
    def __init__(
        self, api_url: str, *, http: httpx.AsyncClient | None = None, max_queue: int = 10_000
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=5.0)
        self._queue: asyncio.Queue[tuple[str, str, object]] = asyncio.Queue(maxsize=max_queue)
        self.dropped = 0

    def _enqueue(self, method: str, path: str, body: object) -> None:
        try:
            self._queue.put_nowait((method, path, body))
        except asyncio.QueueFull:
            self.dropped += 1  # never block a call on reporting

    def log_decision(self, event: DecisionEvent) -> None:
        self._enqueue("POST", "/api/lab/decisions", [event.model_dump(mode="json", by_alias=True)])

    def create_escalation(self, data: EscalationCreate) -> None:
        self._enqueue("POST", "/api/lab/escalations", data.model_dump(mode="json", by_alias=True))

    def consume_escalation(self, escalation_id: str) -> None:
        self._enqueue("POST", f"/api/lab/escalations/{escalation_id}/consume", None)

    async def escalation_statuses(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        try:
            resp = await self._http.get(
                f"{self.api_url}/api/lab/escalations", params=[("ids", i) for i in ids]
            )
            resp.raise_for_status()
            return {e["id"]: e["status"] for e in resp.json()}
        except (httpx.HTTPError, ValueError) as e:
            log.warning("escalation poll failed: %s", e)
            return {}

    async def run(self) -> None:
        """Send queued reports forever (cancel to stop). Retries a few times, then drops."""
        while True:
            method, path, body = await self._queue.get()
            for attempt in range(3):
                try:
                    resp = await self._http.request(method, f"{self.api_url}{path}", json=body)
                    if resp.status_code < 500:
                        break
                except httpx.HTTPError as e:
                    log.warning(
                        "report %s %s failed (attempt %d): %s", method, path, attempt + 1, e
                    )
                await asyncio.sleep(0.2 * (attempt + 1))
            else:
                self.dropped += 1

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait until queued reports are sent (tests / shutdown)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while not self._queue.empty() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
