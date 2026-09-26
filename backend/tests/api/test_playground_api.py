from typing import Any

import pytest

from ..engine.conftest import FakeJev, noul
from ..schema.conftest import noul_rule

REQUEST = {
    "gate": "tool_call",
    "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 620}},
    "reason": "customer asked",
}
GT_500 = {
    "deterministic": {
        "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
        "verdict_when_true": "escalate",
    }
}


def create(c, rid: str, body: dict[str, Any], gate: str = "tool_call") -> None:
    assert (
        c.post("/api/rules", json={"id": rid, "name": rid, "gate": gate, "body": body}).status_code
        == 201
    )


def test_evaluate_scope_draft_vs_live_versions(make_client) -> None:
    c = make_client(jev=FakeJev(answers={"risky": noul(0.9)}))
    create(c, "limit", GT_500)
    # Pin + publish v1 of a Jev rule, then edit it to a draft v2 that would allow.
    create(c, "judge", noul_rule(model="jev-1.13.0"))
    assert c.post("/api/rules/judge/status", json={"status": "live"}).status_code == 200
    v2 = noul_rule(
        model="jev-1.13.0",
        outcomes={"risky": {"type": "noul", "bands": {"escalate_at": 0.95, "deny_at": 0.99}}},
    )
    assert c.put("/api/rules/judge", json={"body": v2}).json()["current_version"] == 2

    live = c.post(
        "/api/evaluate", json={"check_request": REQUEST, "scope": {"kind": "live"}}
    ).json()
    assert live["decision"]["verdict"] == "deny"  # live v1: 0.9 >= 0.7
    assert live["decision"]["versions"]["rules"] == {"judge": 1}
    assert set(live["rules"]) == {"judge"}  # 'limit' is still a draft

    draft = c.post(
        "/api/evaluate", json={"check_request": REQUEST, "scope": {"kind": "draft"}}
    ).json()
    assert (
        draft["decision"]["verdict"] == "escalate"
    )  # draft v2: 0.9 < 0.95 -> allow; limit escalates
    assert draft["decision"]["versions"]["rules"] == {"limit": 1, "judge": 2}
    assert draft["rules"]["judge"]["version"] == 2


def test_evaluate_scope_selected_rules(make_client) -> None:
    c = make_client(jev=FakeJev(answers={"risky": noul(0.9)}))
    create(c, "limit", GT_500)
    create(c, "judge", noul_rule())
    only = c.post(
        "/api/evaluate",
        json={"check_request": REQUEST, "scope": {"kind": "rules", "rule_ids": ["limit"]}},
    ).json()
    assert set(only["rules"]) == {"limit"} and only["decision"]["verdict"] == "escalate"
    missing = c.post(
        "/api/evaluate",
        json={"check_request": REQUEST, "scope": {"kind": "rules", "rule_ids": ["nope"]}},
    )
    assert missing.status_code == 404
    empty = c.post("/api/evaluate", json={"check_request": REQUEST, "scope": {"kind": "rules"}})
    assert empty.status_code == 422


def test_evaluate_stores_run_history(make_client) -> None:
    c = make_client(jev=FakeJev())
    create(c, "limit", GT_500)
    r1 = c.post("/api/evaluate", json={"check_request": REQUEST}).json()
    r2 = c.post(
        "/api/evaluate",
        json={
            "check_request": {
                **REQUEST,
                "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 5}},
            }
        },
    ).json()
    runs = c.get("/api/playground/runs").json()
    assert [r["id"] for r in runs] == [r2["run_id"], r1["run_id"]]
    assert (
        runs[1]["decision"]["verdict"] == "escalate" and runs[0]["decision"]["verdict"] == "allow"
    )
    assert runs[0]["scope"] == {"kind": "draft", "rule_ids": []}


def test_evaluate_malformed_request_422(make_client) -> None:
    c = make_client(jev=FakeJev())
    resp = c.post("/api/evaluate", json={"check_request": {"gate": "tool_call"}})
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"].startswith("check_request")


def test_test_cases_from_playground(make_client) -> None:
    c = make_client(jev=FakeJev())
    create(c, "limit", GT_500)
    tc = c.post(
        "/api/test-cases",
        json={
            "rule_id": "limit",
            "name": "big refund",
            "check_request": REQUEST,
            "expected_verdict": "escalate",
            "origin": "playground",
        },
    )
    assert tc.status_code == 201
    listed = c.get("/api/rules/limit/test-cases").json()
    assert [t["name"] for t in listed] == ["big refund"]
    assert listed[0]["origin"] == "playground" and listed[0]["expected_verdict"] == "escalate"
    bad = c.post(
        "/api/test-cases",
        json={"rule_id": "nope", "name": "x", "check_request": REQUEST, "expected_verdict": "deny"},
    )
    assert bad.status_code == 404


def test_examples_and_packs(make_client) -> None:
    c = make_client(jev=FakeJev())
    examples = c.get("/api/examples").json()
    assert {e["id"] for e in examples} >= {
        "refund-different-card",
        "pii-exfiltration",
        "missing-reason",
        "injection-in-reason",
    }
    packs = {p["name"]: p["rule_ids"] for p in c.get("/api/examples/packs").json()}
    assert "demo" in packs and "refund-over-limit" in packs["demo"]
    first = c.post("/api/examples/packs/demo/load").json()
    assert first["created"] == packs["demo"] and first["skipped"] == []
    again = c.post("/api/examples/packs/demo/load").json()
    assert again["created"] == [] and again["skipped"] == packs["demo"]
    assert c.post("/api/examples/packs/../etc/load").status_code == 404
    assert c.post("/api/examples/packs/nope/load").status_code == 404


@pytest.mark.parametrize(
    "example_id",
    [
        "refund-different-card",
        "pii-exfiltration",
        "missing-reason",
        "injection-in-reason",
        "refund-same-card-ok",
    ],
)
def test_examples_give_expected_verdicts_replayed(make_client, example_id: str) -> None:
    c = make_client()  # replay over committed fixtures recorded live 2026-09-26
    c.post("/api/examples/packs/demo/load")
    ex = next(e for e in c.get("/api/examples").json() if e["id"] == example_id)
    res = c.post(
        "/api/evaluate", json={"check_request": ex["check_request"], "scope": {"kind": "draft"}}
    )
    assert res.status_code == 200, res.text
    assert res.json()["decision"]["verdict"] == ex["expected_verdict"]
