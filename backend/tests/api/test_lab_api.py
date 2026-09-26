from ..engine.conftest import FakeJev

EVENT = {
    "id": "d1",
    "session": "s1",
    "step": 1,
    "gate": "tool_call",
    "tool": "run_shell",
    "verdict": "deny",
    "forwarded": False,
    "check_request": {"gate": "tool_call", "request": {"kind": "tool_call", "tool": "run_shell"}},
}


def test_live_policy_lists_live_rules_only(make_client) -> None:
    c = make_client(jev=FakeJev())
    c.post("/api/examples/packs/demo/load")
    assert c.get("/api/lab/live-policy").json() == {
        "policy_version": None,
        "content_hash": None,
        "rules": [],
    }
    c.post("/api/rules/support-tools-only/status", json={"status": "live"})
    pol = c.get("/api/lab/live-policy").json()
    assert [r["id"] for r in pol["rules"]] == ["support-tools-only"] and pol["policy_version"] == 1
    assert pol["rules"][0]["body"]["deterministic"]["verdict_when_true"] == "deny"


def test_decisions_are_idempotent_and_listed_by_session(make_client) -> None:
    c = make_client(jev=FakeJev())
    assert c.post("/api/lab/decisions", json=[EVENT, EVENT]).status_code == 204
    assert (
        c.post("/api/lab/decisions", json=[{**EVENT, "id": "d2", "session": "s2"}]).status_code
        == 204
    )
    s1 = c.get("/api/lab/decisions?session=s1").json()
    assert [e["id"] for e in s1] == ["d1"] and s1[0]["check_request"]["request"][
        "tool"
    ] == "run_shell"
    assert len(c.get("/api/lab/decisions").json()) == 2


def test_escalation_lifecycle(make_client) -> None:
    c = make_client(jev=FakeJev())
    esc = {"id": "e1", "session": "s1", "tool": "issue_refund", "args_hash": "sha256:x"}
    assert c.post("/api/lab/escalations", json=esc).json()["status"] == "pending"
    assert c.post("/api/lab/escalations", json=esc).status_code == 409
    assert c.post("/api/lab/escalations/e1/consume").status_code == 409  # not approved yet
    assert c.post("/api/lab/escalations/e1/approve").json()["status"] == "approved"
    assert c.post("/api/lab/escalations/e1/deny").status_code == 409
    assert [e["id"] for e in c.get("/api/lab/escalations?status=approved").json()] == ["e1"]
    assert c.get("/api/lab/escalations?ids=e1&ids=nope").json()[0]["status"] == "approved"
    assert c.post("/api/lab/escalations/e1/consume").json()["status"] == "consumed"
    assert c.post("/api/lab/escalations/nope/approve").status_code == 404
