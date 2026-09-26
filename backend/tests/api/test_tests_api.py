import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from precheck.jev import JevResponse, JevUnavailable
from precheck.schema import JevUsage

from ..engine.conftest import FakeJev
from ..translator.conftest import FakeLLM, draft_test

JEV_BODY = {
    "applies_when": {"op": "eq", "path": "request.tool", "value": "issue_refund"},
    "severity": "high",
    "jev": {
        "model": "jev-latest",
        "state_template": ["request"],
        "questions": {"q": {"type": "noul", "instructions": "Different card?"}},
        "outcomes": {"q": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.99}}},
    },
}


def req(dest: str) -> dict[str, Any]:
    return {
        "gate": "tool_call",
        "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"to": dest}},
    }


@dataclass
class ByDestJev:
    """Probability by destination; counts calls and peak concurrency."""

    probs: dict[str, float]
    delay: float = 0.0
    fail_for: str | None = None
    calls: int = 0
    in_flight: int = 0
    peak: int = 0
    seen: list[Any] = field(default_factory=list)

    async def evaluate(
        self, state: Any, questions: dict[str, Any], model: str = "jev-latest"
    ) -> JevResponse:
        self.calls += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            dest = state["request"]["args"]["to"]
            if dest == self.fail_for:
                raise JevUnavailable("503 from Jev")
            return JevResponse(
                resolved_model="jev-1.13.0",
                answers={nid: {"type": "noul", "noul": self.probs[dest]} for nid in questions},
                usage=JevUsage(input_tokens=500),
            )
        finally:
            self.in_flight -= 1


def setup(c, cases: list[tuple[str, str]]) -> None:
    assert (
        c.post(
            "/api/rules", json={"id": "card", "name": "Card", "gate": "tool_call", "body": JEV_BODY}
        ).status_code
        == 201
    )
    for dest, expected in cases:
        assert (
            c.post(
                "/api/test-cases",
                json={
                    "rule_id": "card",
                    "name": dest,
                    "check_request": req(dest),
                    "expected_verdict": expected,
                },
            ).status_code
            == 201
        )


def test_run_calibrate_apply_rerun(make_client) -> None:
    jev = ByDestJev({"same": 0.03, "other": 0.96, "vague": 0.55})
    c = make_client(jev=jev)
    setup(c, [("same", "allow"), ("other", "deny"), ("vague", "escalate")])

    run = c.post("/api/test-runs", json={"scope": "rule", "rule_id": "card"}).json()
    assert (run["pass_count"], run["fail_count"], run["error_count"]) == (
        2,
        1,
        0,
    )  # 0.96 < deny_at 0.99
    failing = next(r for r in run["results"] if not r["passed"])
    assert (
        failing["name"] == "other"
        and failing["actual"] == "escalate"
        and failing["jev"]["card"]["q"]["value"] == 0.96
    )
    assert run["jev_model"] == "jev-1.13.0" and run["input_tokens"] == 1500
    assert run["cost_estimate"] == pytest.approx(1500 * 0.042 / 1_000_000)

    calls_before = jev.calls
    cal = c.post("/api/rules/card/calibrate").json()
    assert jev.calls == calls_before  # calibrate_no_calls
    [q] = cal["questions"]
    assert q["current"]["correct"] == 2 and q["suggested"]["correct"] == 3
    suggested = q["suggested"]["bands"]
    assert suggested["deny_at"] <= 0.96 and 0.03 < suggested["escalate_at"] <= 0.55

    applied = c.post("/api/rules/card/apply-bands", json={"bands": {"q": suggested}}).json()
    assert applied["created_version"] and applied["current_version"] == 2
    rerun = c.post("/api/test-runs", json={"scope": "rule", "rule_id": "card"}).json()
    assert (rerun["pass_count"], rerun["fail_count"]) == (3, 0)

    listed = c.get("/api/test-runs?rule_id=card").json()
    assert [r["id"] for r in listed] == [rerun["id"], run["id"]] and listed[0]["results"] == []
    detail = c.get(f"/api/test-runs/{run['id']}").json()
    assert len(detail["results"]) == 3 and detail["results"][1]["jev"]["card"]["q"][
        "band"
    ].startswith("escalate")


def test_calibrate_no_calls_uses_stored_answers_of_a_specific_run(make_client) -> None:
    jev = ByDestJev({"same": 0.03, "other": 0.96})
    c = make_client(jev=jev)
    setup(c, [("same", "allow"), ("other", "deny")])
    run = c.post("/api/test-runs", json={"scope": "rule", "rule_id": "card"}).json()
    n = jev.calls
    for _ in range(3):
        assert c.post(f"/api/rules/card/calibrate?run_id={run['id']}").status_code == 200
    assert jev.calls == n


def test_runner_concurrency_cap(make_client) -> None:
    jev = ByDestJev({f"d{i}": 0.1 for i in range(20)}, delay=0.02)
    c = make_client(jev=jev)
    setup(c, [(f"d{i}", "allow") for i in range(20)])
    run = c.post("/api/test-runs", json={"scope": "rule", "rule_id": "card"}).json()
    assert run["pass_count"] == 20
    assert 1 < jev.peak <= 8  # bounded, and actually concurrent


def test_runner_records_partial_failures(make_client) -> None:
    jev = ByDestJev({"same": 0.03, "broken": 0.0}, fail_for="broken")
    c = make_client(jev=jev)
    setup(c, [("same", "allow"), ("broken", "deny")])
    run = c.post("/api/test-runs", json={"scope": "rule", "rule_id": "card"}).json()
    assert (run["pass_count"], run["error_count"]) == (1, 1)
    broken = next(r for r in run["results"] if r["name"] == "broken")
    assert (
        "503 from Jev" in broken["error"] and broken["actual"] == "escalate"
    )  # on_error default (high)


def test_policy_scope_and_live_scope(make_client) -> None:
    c = make_client(jev=FakeJev(answers={"q": {"type": "noul", "noul": 0.1}}))
    setup(c, [("same", "allow")])
    c.post(
        "/api/test-cases",
        json={"name": "policy-wide", "check_request": req("x"), "expected_verdict": "allow"},
    )
    run = c.post("/api/test-runs", json={"scope": "policy"}).json()
    assert run["pass_count"] == 2
    missing = c.post(
        "/api/test-runs", json={"scope": "rule", "rule_id": "card", "rule_status": "live"}
    )
    assert missing.status_code == 409 and "no live version" in missing.json()["detail"]


def test_calibrate_errors(make_client) -> None:
    c = make_client(jev=FakeJev())
    setup(c, [])
    assert c.post("/api/rules/card/calibrate").status_code == 409  # no run yet
    c.post(
        "/api/rules",
        json={
            "id": "code",
            "name": "Code",
            "gate": "tool_call",
            "body": {
                "deterministic": {
                    "predicate": {"op": "exists", "path": "reason"},
                    "verdict_when_true": "deny",
                }
            },
        },
    )
    assert "no Jev check" in c.post("/api/rules/code/calibrate").json()["detail"]
    assert c.post("/api/rules/nope/calibrate").status_code == 404


def test_test_case_crud(make_client) -> None:
    c = make_client(jev=FakeJev())
    setup(c, [("same", "allow")])
    [tc] = c.get("/api/test-cases?rule_id=card").json()
    upd = c.put(
        f"/api/test-cases/{tc['id']}", json={"expected_verdict": "deny", "name": "renamed"}
    ).json()
    assert upd["expected_verdict"] == "deny" and upd["name"] == "renamed"
    assert c.delete(f"/api/test-cases/{tc['id']}").status_code == 204
    assert c.get(f"/api/test-cases/{tc['id']}").status_code == 404
    assert c.get("/api/test-cases?policy=true").json() == []


def test_generate_tests_on_demand(make_client) -> None:
    llm = FakeLLM(
        {
            "tests": [
                {
                    "tests": [
                        draft_test("card", expected_verdict="allow"),
                        draft_test("card", name="n2"),
                    ]
                }
            ]
        }
    )
    c = make_client(jev=FakeJev(), llm=llm)
    setup(c, [])
    out = c.post("/api/rules/card/generate-tests").json()
    assert len(out["created"]) == 2 and out["created"][0]["origin"] == "generated"
    assert len(c.get("/api/rules/card/test-cases").json()) == 2
    assert "Rules from step 2" in llm.calls[0]["messages"][0]["content"]
