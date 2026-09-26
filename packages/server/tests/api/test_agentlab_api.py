import httpx
import respx

AGENT = "http://agent.test:8300"


def test_scenarios_listed(make_client) -> None:
    ids = [s["id"] for s in make_client().get("/api/lab/scenarios").json()]
    assert len(ids) == 9 and "pii-exfiltration" in ids


@respx.mock
def test_start_run_is_relayed(make_client) -> None:
    route = respx.post(f"{AGENT}/runs").mock(
        return_value=httpx.Response(202, json={"id": "r1", "status": "running"})
    )
    c = make_client(agent_url=AGENT)
    resp = c.post("/api/lab/runs/start", json={"mode": "scripted", "scenario_id": "happy-refund"})
    assert resp.status_code == 202 and resp.json() == {"id": "r1", "status": "running"}
    assert (
        route.calls[0].request.content
        == b'{"mode":"scripted","scenario_id":"happy-refund","goal":null,"agent_id":null}'
    )
    assert c.post("/api/lab/runs/start", json={"mode": "llm"}).status_code == 422


@respx.mock
def test_agent_errors_become_problems(make_client) -> None:
    respx.post(f"{AGENT}/runs").mock(
        return_value=httpx.Response(503, json={"detail": "LLM mode is not configured"})
    )
    respx.post(f"{AGENT}/runs/r1/retry/2").mock(
        return_value=httpx.Response(404, json={"detail": "run 'r1' not found"})
    )
    c = make_client(agent_url=AGENT)
    llm = c.post("/api/lab/runs/start", json={"mode": "llm", "goal": "x"})
    assert llm.status_code == 503 and llm.json()["detail"] == "LLM mode is not configured"
    assert c.post("/api/lab/runs/r1/retry/2").status_code == 404


def test_agent_unreachable_is_503(make_client) -> None:
    c = make_client(agent_url="http://127.0.0.1:1")
    resp = c.post("/api/lab/runs/start", json={"mode": "scripted", "scenario_id": "happy-refund"})
    assert resp.status_code == 503 and resp.json()["title"] == "Test agent unavailable"


@respx.mock
def test_events_are_relayed(make_client) -> None:
    body = b'event: step\ndata: {"index": 1}\n\nevent: done\ndata: {"status": "passed"}\n\n'
    respx.get(f"{AGENT}/runs/r1/events").mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )
    )
    c = make_client(agent_url=AGENT)
    with c.stream("GET", "/api/lab/runs/r1/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())
    assert text == body.decode()


@respx.mock
def test_events_unknown_run(make_client) -> None:
    respx.get(f"{AGENT}/runs/nope/events").mock(
        return_value=httpx.Response(404, json={"detail": "x"})
    )
    with make_client(agent_url=AGENT).stream("GET", "/api/lab/runs/nope/events") as resp:
        assert "event: error" in "".join(resp.iter_text())
