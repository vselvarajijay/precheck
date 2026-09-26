import asyncio
import json

from fastapi.testclient import TestClient

from precheck.core.schema.lab import LabRun, RunStep
from precheck.lab.agent import service
from precheck.lab.settings import LabSettings as Settings


def test_sse_stream_emits_steps_in_order(monkeypatch) -> None:
    async def fake_run_scenario(scenario, proxy, api, *, run_id, on_step):  # type: ignore[no-untyped-def]
        run = LabRun(
            id=run_id,
            mode="scripted",
            scenario_id=scenario.id,
            agent_id="support-bot",
            status="running",
        )
        for i in range(1, 4):
            await asyncio.sleep(0.05)
            step = RunStep(index=i, tool=f"t{i}", verdict="allow", reached_tool=True, passed=True)
            run.steps.append(step)
            await on_step(run, step)
        run.status = "passed"
        return run

    monkeypatch.setattr(service, "run_scenario", fake_run_scenario)
    with TestClient(service.create_app()) as client:
        started = client.post("/runs", json={"mode": "scripted", "scenario_id": "happy-refund"})
        assert started.status_code == 202
        run_id = started.json()["id"]
        with client.stream("GET", f"/runs/{run_id}/events") as resp:
            events = []
            name = None
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    name = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    events.append((name, json.loads(line.removeprefix("data: "))))
                    if name == "done":
                        break
    assert [n for n, _ in events] == ["step", "step", "step", "done"]
    assert [d["index"] for n, d in events if n == "step"] == [1, 2, 3]
    assert events[-1][1]["status"] == "passed"


def test_start_validation_and_llm_not_configured(monkeypatch) -> None:
    settings = Settings(_env_file=None, anthropic_api_key=None, llm_mode="live")  # type: ignore[call-arg]
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    with TestClient(service.create_app()) as client:
        assert client.post("/runs", json={"mode": "scripted"}).status_code == 422
        assert (
            client.post("/runs", json={"mode": "scripted", "scenario_id": "nope"}).status_code
            == 404
        )
        resp = client.post("/runs", json={"mode": "llm", "goal": "refund my order"})
        assert resp.status_code == 503 and "not configured" in resp.json()["detail"]
        assert len(client.get("/scenarios").json()) == 9
        assert client.get("/health").json()["llm_configured"] is False
