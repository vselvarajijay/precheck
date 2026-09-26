import sqlite3
from pathlib import Path

import yaml

from precheck.core.testing import FakeJev, noul

REQ = {
    "gate": "tool_call",
    "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 5}},
}


def jev_body(model: str = "jev-latest", deny_at: float = 0.7) -> dict:
    return {
        "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"},
        "jev": {
            "model": model,
            "state_template": ["request"],
            "questions": {"q": {"type": "noul", "instructions": "Is it bad?"}},
            "outcomes": {"q": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": deny_at}}},
        },
    }


def make(c, rid: str, body: dict, tests: list[tuple[str, str]] = ()) -> None:
    assert (
        c.post(
            "/api/rules",
            json={
                "id": rid,
                "name": rid.title(),
                "gate": "tool_call",
                "body": body,
                "source_text": f"{rid} source",
            },
        ).status_code
        == 201
    )
    for name, verdict in tests:
        c.post(
            "/api/test-cases",
            json={"rule_id": rid, "name": name, "check_request": REQ, "expected_verdict": verdict},
        )


def test_publish_pins_model_runs_tests_and_snapshots(make_client, db_path: Path) -> None:
    c = make_client(jev=FakeJev(answers={"q": noul(0.9)}, model="jev-1.13.0"))
    make(c, "card", jev_body(), [("bad", "deny"), ("oops", "allow")])
    res = c.post("/api/rules/card/publish").json()
    assert (res["pinned_from"], res["pinned_to"]) == ("jev-latest", "jev-1.13.0")
    rule = res["rule"]
    assert rule["status"] == "live" and rule["live_version"] == 2 == rule["current_version"]
    assert rule["live"]["body"]["jev"]["model"] == "jev-1.13.0"
    assert res["test_run"]["pass_count"] == 1 and res["test_run"]["jev_model"] == "jev-1.13.0"
    assert res["warnings"] == ["1 of 2 test case(s) fail on jev-1.13.0"]
    assert res["policy_version"]["version"] == 1
    assert res["policy_version"]["rules"] == [
        {"rule_id": "card", "version": 2, "content_hash": rule["live"]["content_hash"]}
    ]
    # No live rule is ever unpinned (V2 query).
    with sqlite3.connect(db_path) as con:
        n = con.execute(
            "select count(*) from rule_versions v join rules r on r.live_version_id=v.id "
            "where r.status='live' and v.jev_model in ('jev-latest','jev-preview')"
        ).fetchone()[0]
    assert n == 0


def test_publish_without_tests_warns_and_deterministic_needs_no_pin(make_client) -> None:
    c = make_client(jev=FakeJev())
    make(
        c,
        "limit",
        {
            "deterministic": {
                "predicate": {"op": "gt", "path": "request.args.amount", "value": 1},
                "verdict_when_true": "escalate",
            }
        },
    )
    res = c.post("/api/rules/limit/publish").json()
    assert res["pinned_to"] is None and res["rule"]["current_version"] == 1
    assert res["warnings"] == ["rule has no test cases; publish without a golden set"]


def test_rollback_restores_exact_snapshot(make_client) -> None:
    c = make_client(jev=FakeJev(answers={"q": noul(0.1)}, model="jev-1.13.0"))
    make(c, "a", jev_body())
    make(c, "b", jev_body())
    v1 = c.post("/api/rules/a/publish").json()["policy_version"]
    c.put("/api/rules/a", json={"body": jev_body("jev-1.13.0", deny_at=0.8)})
    c.post("/api/rules/a/publish")
    v3 = c.post("/api/rules/b/publish").json()["policy_version"]
    assert v3["version"] == 3 and {r["rule_id"] for r in v3["rules"]} == {"a", "b"}
    back = c.post(f"/api/policy-versions/{v1['version']}/activate").json()
    assert back["version"] == 4 and back["note"] == "rollback to v1"
    assert back["content_hash"] == v1["content_hash"] and back["rules"] == v1["rules"]
    assert c.get("/api/rules/a").json()["live_version"] == 2
    assert c.get("/api/rules/b").json()["status"] == "draft"
    versions = c.get("/api/policy-versions").json()
    assert [v["version"] for v in versions] == [4, 3, 2, 1] and versions[0]["active"]
    assert c.post("/api/policy-versions/99/activate").status_code == 404


def test_status_changes_snapshot_policy(make_client) -> None:
    c = make_client(jev=FakeJev())
    make(c, "a", jev_body("jev-1.13.0"))
    c.post("/api/rules/a/status", json={"status": "live"})
    c.post("/api/rules/a/status", json={"status": "draft"})
    notes = [v["note"] for v in c.get("/api/policy-versions").json()]
    assert notes == ["a -> draft (v1)", "a -> live (v1)"]


def test_yaml_round_trip(make_client, tmp_path, migrated_template) -> None:
    jev = FakeJev(answers={"q": noul(0.1)}, model="jev-1.13.0")
    c = make_client(jev=jev)
    make(c, "a", jev_body(), [("fine", "allow")])
    make(
        c,
        "limit",
        {
            "deterministic": {
                "predicate": {"op": "gt", "path": "request.args.amount", "value": 1},
                "verdict_when_true": "escalate",
            }
        },
        [("big", "allow")],
    )
    c.post("/api/rules/a/publish")
    c.post("/api/rules/limit/publish")
    first = c.get("/api/export")
    assert first.headers["content-type"].startswith("application/yaml")
    exported = yaml.safe_load(first.text)
    assert exported["schema"] == 1 and [r["id"] for r in exported["rules"]] == ["a", "limit"]
    assert (
        exported["rules"][0]["provenance"]["jev_model"] == "jev-1.13.0"
        and exported["rules"][0]["tests"]
    )

    # Fresh database: import -> drafts only -> publish -> export again.
    import shutil

    fresh = tmp_path / "fresh.db"
    shutil.copy(migrated_template, fresh)
    c2 = make_client(jev=jev, db_path=fresh)
    imported = c2.post("/api/import", json={"yaml": first.text}).json()
    assert imported["created"] == ["a", "limit"] and imported["tests_created"] == 2
    assert {r["status"] for r in c2.get("/api/rules").json()} == {"draft"}  # never auto-live
    for rid in imported["created"]:
        c2.post(f"/api/rules/{rid}/publish")
    second = yaml.safe_load(c2.get("/api/export").text)
    for d in (exported, second):
        for r in d["rules"]:
            r.pop("version", None)
    assert second == exported


def test_import_validation_and_renames(make_client) -> None:
    c = make_client(jev=FakeJev())
    bad = c.post("/api/import", json={"yaml": "schema: 2\nrules: []\n"})
    assert bad.status_code == 422 and bad.json()["errors"]
    assert c.post("/api/import", json={"yaml": "rules: [unclosed"}).status_code == 422
    make(c, "a", jev_body())
    pack = {
        "schema": 1,
        "rules": [{"id": "a", "name": "A", "gate": "tool_call", "body": jev_body()}],
    }
    res = c.post("/api/import", json={"yaml": yaml.safe_dump(pack)}).json()
    assert res["renamed"] == {"a": "a-2"}
    assert c.get("/api/export").status_code == 409  # nothing live yet


def test_upgrade_check_reports_diffs(make_client) -> None:
    jev = FakeJev(
        model="jev-1.13.0",
        answers={"q": noul(0.1)},
        by_model={"jev-1.13.0": {"q": noul(0.1)}, "jev-1.14.0": {"q": noul(0.8)}},
    )
    c = make_client(jev=jev)
    make(c, "a", jev_body(), [("fine", "allow")])
    c.post("/api/rules/a/publish")
    report = c.post("/api/jev/upgrade-check", json={"target_model": "jev-1.14.0"}).json()
    assert report["rules_checked"] == 1 and report["cases_checked"] == 1
    assert (report["current_pass"], report["target_pass"]) == (1, 0)
    [d] = report["diffs"]
    assert (d["current"], d["target"], d["current_values"], d["target_values"]) == (
        "allow",
        "deny",
        [0.1],
        [0.8],
    )
    assert (
        c.get("/api/rules/a").json()["live"]["body"]["jev"]["model"] == "jev-1.13.0"
    )  # nothing published
    assert c.post("/api/jev/upgrade-check", json={"target_model": "gpt"}).status_code == 422


def test_diff_endpoint(make_client) -> None:
    c = make_client(jev=FakeJev(model="jev-1.13.0", answers={"q": noul(0.1)}))
    make(c, "a", jev_body(), [("fine", "allow")])
    c.post("/api/rules/a/publish")
    same = c.get("/api/rules/a/diff").json()
    assert same["changed"] is False and same["draft_run"]["pass_count"] == 1
    c.put("/api/rules/a", json={"body": jev_body("jev-1.13.0", deny_at=0.9)})
    changed = c.get("/api/rules/a/diff").json()
    assert (
        changed["changed"] and changed["live"]["version"] == 2 and changed["draft"]["version"] == 3
    )
