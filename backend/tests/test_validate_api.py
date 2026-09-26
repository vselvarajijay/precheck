from .schema.conftest import noul_rule


def test_validate_rule_body_ok(make_client) -> None:
    resp = make_client().post("/api/validate/rule-body", json=noul_rule())
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_hash"].startswith("sha256:")
    assert body["jev_model"] == "jev-latest"
    assert any("must pin a Jev version" in p for p in body["live_problems"])


def test_validate_rule_body_pinned_is_publishable(make_client) -> None:
    resp = make_client().post("/api/validate/rule-body", json=noul_rule(model="jev-1.13.0"))
    assert resp.json()["live_problems"] == []


def test_validate_rule_body_invalid_is_422(make_client) -> None:
    resp = make_client().post("/api/validate/rule-body", json={})
    assert resp.status_code == 422
    assert "needs a deterministic check" in resp.text


def test_validate_check_request(make_client) -> None:
    client = make_client()
    ok = client.post(
        "/api/validate/check-request",
        json={"gate": "egress", "request": {"kind": "content", "text": "hi"}},
    )
    assert ok.status_code == 200
    assert client.post("/api/validate/check-request", json={"gate": "egress"}).status_code == 422
