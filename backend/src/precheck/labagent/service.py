"""Test-agent service: start runs, watch them live.

POST /runs {mode: scripted, scenario_id} | {mode: llm, goal, agent_id?}   -> {id}
GET  /runs/{id}            the run so far
GET  /runs/{id}/events     server-sent events: `step` per step, then `done`
GET  /scenarios, /health

uvicorn precheck.labagent.service:app --port 8300
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from precheck.config import get_settings
from precheck.enforcement.agents import AgentProfiles
from precheck.labagent.reporting import LabApi
from precheck.labagent.runner import ClaudeAgentLLM, run_llm, run_scenario
from precheck.labagent.scenarios import get_scenario, load_scenarios
from precheck.schema.lab import LabRun, RunStep
from precheck.schema.scenario import Scenario


class StartRun(BaseModel):
    mode: Literal["scripted", "llm"]
    scenario_id: str | None = None
    goal: str | None = None
    agent_id: str | None = None

    @model_validator(mode="after")
    def _inputs(self) -> "StartRun":
        if self.mode == "scripted" and not self.scenario_id:
            raise ValueError("scripted runs need scenario_id")
        if self.mode == "llm" and not (self.goal and self.goal.strip()):
            raise ValueError("llm runs need a goal")
        return self


class Started(BaseModel):
    id: str
    status: str


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="precheck lab agent")
    runs: dict[str, LabRun] = {}
    listeners: dict[str, list[asyncio.Queue[tuple[str, str]]]] = {}
    tasks: set[asyncio.Task[LabRun]] = set()
    scenarios_dir = settings.examples_dir / "scenarios"
    agents = AgentProfiles.load(settings.proxy_agents_file, default=settings.proxy_default_agent)

    async def publish(run_id: str, event: str, data: str) -> None:
        for q in listeners.get(run_id, []):
            q.put_nowait((event, data))

    async def on_step(run: LabRun, step: RunStep) -> None:
        runs[run.id] = run
        await publish(run.id, "step", step.model_dump_json(by_alias=True))

    def api() -> LabApi:
        return LabApi(settings.api_url, settings.agent_tools_url)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "proxy": settings.agent_proxy_url,
            "llm_configured": settings.anthropic_configured
            or settings.llm_mode in ("replay", "cache"),
        }

    @app.get("/scenarios", response_model=list[Scenario])
    def scenarios() -> list[Scenario]:
        return load_scenarios(scenarios_dir)

    @app.post("/runs", response_model=Started, status_code=202)
    async def start(req: StartRun) -> Started:
        run_id = str(uuid.uuid4())
        if req.mode == "scripted":
            scenario = get_scenario(scenarios_dir, req.scenario_id or "")
            if scenario is None:
                raise HTTPException(404, f"scenario {req.scenario_id!r} not found")
            runs[run_id] = LabRun(
                id=run_id,
                mode="scripted",
                scenario_id=scenario.id,
                goal=scenario.user_goal,
                agent_id=scenario.agent.id,
                status="running",
            )
            coro = run_scenario(
                scenario, settings.agent_proxy_url, api(), run_id=run_id, on_step=on_step
            )
        else:
            if not settings.anthropic_configured and settings.llm_mode == "live":
                raise HTTPException(
                    503, "LLM mode is not configured: set ANTHROPIC_API_KEY (scripted runs work)"
                )
            agent = agents.resolve(req.agent_id)
            agent_id = agent.id if agent and agent.id else "agent"
            llm = ClaudeAgentLLM(
                settings.anthropic_api_key.get_secret_value()
                if settings.anthropic_api_key
                else None,
                settings.agent_model,
                mode=settings.llm_mode,
                fixtures_dir=settings.llm_fixtures_dir,
            )
            runs[run_id] = LabRun(
                id=run_id, mode="llm", goal=req.goal, agent_id=agent_id, status="running"
            )
            coro = run_llm(
                req.goal or "",
                agent_id,
                agent.purpose if agent else None,
                llm,
                settings.agent_proxy_url,
                api(),
                max_turns=settings.agent_max_turns,
                run_id=run_id,
                on_step=on_step,
            )

        async def execute() -> LabRun:
            run = await coro
            runs[run.id] = run
            await publish(run.id, "done", run.model_dump_json(by_alias=True))
            return run

        task = asyncio.create_task(execute())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return Started(id=run_id, status="running")

    @app.get("/runs/{run_id}", response_model=LabRun)
    def get_run(run_id: str) -> LabRun:
        if run_id not in runs:
            raise HTTPException(404, f"run {run_id!r} not found")
        return runs[run_id]

    @app.get("/runs/{run_id}/events")
    async def events(run_id: str) -> StreamingResponse:
        if run_id not in runs:
            raise HTTPException(404, f"run {run_id!r} not found")
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        listeners.setdefault(run_id, []).append(queue)

        async def stream() -> AsyncIterator[str]:
            try:
                run = runs[run_id]
                for step in run.steps:  # catch up
                    yield f"event: step\ndata: {step.model_dump_json(by_alias=True)}\n\n"
                if run.status != "running":
                    yield f"event: done\ndata: {run.model_dump_json(by_alias=True)}\n\n"
                    return
                sent = len(run.steps)
                while True:
                    event, data = await queue.get()
                    if event == "step" and json.loads(data)["index"] <= sent:
                        continue
                    yield f"event: {event}\ndata: {data}\n\n"
                    if event == "done":
                        return
            finally:
                listeners[run_id].remove(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    return app


app = create_app()
