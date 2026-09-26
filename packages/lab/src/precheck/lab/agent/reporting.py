"""Persist runs/steps in the API and read the proxy's decision log + tools' call log."""

import asyncio
import logging
from typing import Any

import httpx

from precheck.core.schema.lab import DecisionEvent, LabRun, RunStep

log = logging.getLogger("precheck.lab.agent")


class LabApi:
    def __init__(self, api_url: str, tools_url: str, http: httpx.AsyncClient | None = None) -> None:
        self.api_url = api_url.rstrip("/")
        self.tools_url = tools_url.rstrip("/")
        self.http = http or httpx.AsyncClient(timeout=10.0)

    async def put_run(self, run: LabRun) -> None:
        header = run.model_copy(update={"steps": []})
        await self._put(f"/api/lab/runs/{run.id}", header.model_dump(mode="json", by_alias=True))

    async def put_step(self, run_id: str, step: RunStep) -> None:
        await self._put(
            f"/api/lab/runs/{run_id}/steps/{step.index}",
            step.model_dump(mode="json", by_alias=True),
        )

    async def _put(self, path: str, body: Any) -> None:
        try:
            (await self.http.put(f"{self.api_url}{path}", json=body)).raise_for_status()
        except httpx.HTTPError as e:  # reporting never stops a run
            log.warning("could not persist %s: %s", path, e)

    async def tool_calls(self, session: str) -> list[dict[str, Any]]:
        try:
            resp = await self.http.get(f"{self.tools_url}/calls", params={"session": session})
            resp.raise_for_status()
            return list(resp.json())
        except httpx.HTTPError as e:
            log.warning("tools call log unavailable: %s", e)
            return []

    async def step_decisions(
        self, session: str, step: int, wait_s: float = 3.0, grace_s: float = 0.3
    ) -> list[DecisionEvent]:
        """The proxy logs asynchronously: wait for the step's tool_call event, then a short
        grace period for its ingress event (if the result was checked)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        seen_at: float | None = None
        events: list[DecisionEvent] = []
        while loop.time() < deadline:
            try:
                resp = await self.http.get(
                    f"{self.api_url}/api/lab/decisions", params={"session": session}
                )
                resp.raise_for_status()
                events = [
                    e
                    for e in (DecisionEvent.model_validate(x) for x in resp.json())
                    if e.step == step
                ]
            except httpx.HTTPError as e:
                log.warning("decision log unavailable: %s", e)
            if any(e.gate == "tool_call" for e in events):
                seen_at = seen_at or loop.time()
                if len(events) >= 2 or loop.time() - seen_at >= grace_s:
                    break
            await asyncio.sleep(0.05)
        return sorted(events, key=lambda e: e.gate != "tool_call")
