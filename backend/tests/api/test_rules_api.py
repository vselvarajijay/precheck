from typing import Any

from ..schema.conftest import noul_rule


def new_rule(client, **over: Any) -> dict[str, Any]:
    payload = {"name": "Refund different method", "gate": "tool_call", "body": noul_rule(), **over}
    resp = client.post("/api/rules", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_crud_flow(make_client) -> None:
    c = make_client()
    r = new_rule(c, source_text="Never refund to a different card.")
    rid = r["id"]
    assert r["current_version"] == 1 and r["status"] == "draft" and r["has_jev"]
    assert c.get(f"/api/rules/{rid}").json()["current"]["source_text"].startswith("Never")
    body2 = noul_rule(questions={"risky": {"type": "noul", "instructions": "Different card?"}})
    u = c.put(f"/api/rules/{rid}", json={"body": body2}).json()
    assert u["created_version"] is True and u["current_version"] == 2
    same = c.put(f"/api/rules/{rid}", json={"body": body2}).json()
    assert same["created_version"] is False
    assert [v["version"] for v in same["versions"]] == [1, 2]
    v1 = c.get(f"/api/rules/{rid}/versions/1").json()
    assert v1["body"]["jev"]["questions"]["risky"]["instructions"] == "Is this risky?"
    assert [x["id"] for x in c.get("/api/rules").json()] == [rid]


def test_404s_are_problem_json(make_client) -> None:
    c = make_client()
    for method, path in [
        ("get", "/api/rules/nope"),
        ("get", "/api/rules/nope/versions/1"),
        ("delete", "/api/rules/nope"),
    ]:
        resp = getattr(c, method)(path)
        assert resp.status_code == 404
        assert resp.headers["content-type"] == "application/problem+json"
        assert resp.json()["title"] == "Not found"
    rid = new_rule(c)["id"]
    assert c.get(f"/api/rules/{rid}/versions/9").status_code == 404


def test_invalid_body_is_422_problem(make_client) -> None:
    c = make_client()
    resp = c.post("/api/rules", json={"name": "x", "gate": "tool_call", "body": {}})
    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/problem+json"
    problem = resp.json()
    assert problem["title"] == "Invalid request"
    assert any("needs a deterministic check" in e["message"] for e in problem["errors"])


def test_live_guard_names_field(make_client) -> None:
    c = make_client()
    rid = new_rule(c)["id"]
    resp = c.post(f"/api/rules/{rid}/status", json={"status": "live"})
    assert resp.status_code == 422
    problem = resp.json()
    assert problem["errors"][0]["field"] == "body.jev.model"
    assert "must pin a Jev version" in problem["errors"][0]["message"]
    c.put(f"/api/rules/{rid}", json={"body": noul_rule(model="jev-1.13.0")})
    ok = c.post(f"/api/rules/{rid}/status", json={"status": "live"})
    assert ok.status_code == 200 and ok.json()["live_version"] == 2


def test_archive_hides_by_default(make_client) -> None:
    c = make_client()
    rid = new_rule(c)["id"]
    assert c.delete(f"/api/rules/{rid}").json()["status"] == "archived"
    assert c.get("/api/rules").json() == []
    assert [r["id"] for r in c.get("/api/rules?status=archived").json()] == [rid]
    assert c.put(f"/api/rules/{rid}", json={"body": noul_rule()}).status_code == 409


def test_list_filters_via_query(make_client) -> None:
    c = make_client()
    new_rule(c, name="A", gate="egress")
    new_rule(c, name="B")
    assert [r["id"] for r in c.get("/api/rules?gate=egress").json()] == ["a"]
    assert c.get("/api/rules?gate=sideways").status_code == 422


def test_applies_to_tools_summary(make_client) -> None:
    c = make_client()
    body = noul_rule() | {
        "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"}
    }
    r = new_rule(c, body=body)
    assert r["applies_to_tools"] == ["issue_refund"]
