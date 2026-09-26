"""Agent Lab endpoints for the UI: scenarios, and relays to the test-agent service
(start runs, retry a step, live SSE). Runs/decisions/escalations are in api/lab.py."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from precheck.api.deps import SettingsDep
from precheck.api.problems import PROBLEM_RESPONSES
from precheck.authoring.errors import NotFoundError, ServiceError
from precheck.labagent.scenarios import load_scenarios
from precheck.labagent.service import Started, StartRun
from precheck.schema.lab import RunStep
from precheck.schema.scenario import Scenario

router = APIRouter(prefix="/api/lab", tags=["agent-lab"], responses=PROBLEM_RESPONSES)


class AgentUnavailable(ServiceError):
    status = 503
    title = "Test agent unavailable"


def _raise_for(resp: httpx.Response) -> None:
    if resp.status_code == 404:
        raise NotFoundError(resp.json().get("detail", "not found"))
    if resp.status_code >= 400:
        detail: Any = (
            resp.json().get("detail")
            if resp.headers.get("content-type", "").startswith("application/json")
            else resp.text
        )
        raise AgentUnavailable(str(detail))


@router.get("/scenarios", response_model=list[Scenario])
def scenarios(settings: SettingsDep) -> list[Scenario]:
    return load_scenarios(settings.examples_dir / "scenarios")


@router.post("/runs/start", response_model=Started, status_code=202)
async def start_run(req: StartRun, settings: SettingsDep) -> Started:
    """Start a scripted scenario or an LLM goal on the test agent."""
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(f"{settings.agent_url}/runs", json=req.model_dump(mode="json"))
    except httpx.HTTPError as e:
        raise AgentUnavailable(f"cannot reach the test agent at {settings.agent_url}: {e}") from e
    _raise_for(resp)
    return Started.model_validate(resp.json())


@router.post("/runs/{run_id}/retry/{index}", response_model=RunStep)
async def retry(run_id: str, index: int, settings: SettingsDep) -> RunStep:
    """Repeat a step in the same agent session (e.g. after approving its escalation)."""
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(f"{settings.agent_url}/runs/{run_id}/retry/{index}")
    except httpx.HTTPError as e:
        raise AgentUnavailable(str(e)) from e
    _raise_for(resp)
    return RunStep.model_validate(resp.json())


@router.get("/runs/{run_id}/events")
async def events(run_id: str, settings: SettingsDep) -> StreamingResponse:
    """Relay the agent's server-sent events for a run."""

    async def relay() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=None)) as http:
            try:
                async with http.stream("GET", f"{settings.agent_url}/runs/{run_id}/events") as resp:
                    if resp.status_code != 200:
                        yield b'event: error\ndata: {"detail": "run not found on the agent"}\n\n'
                        return
                    async for chunk in resp.aiter_raw():
                        yield chunk
            except httpx.HTTPError as e:
                msg = f'{{"detail": "agent unavailable: {type(e).__name__}"}}'
                yield f"event: error\ndata: {msg}\n\n".encode()

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
