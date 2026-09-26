from dataclasses import dataclass, field
from typing import Any

import pytest

from precheck.core.scenarios import get_scenario, load_scenarios
from precheck.core.schema.lab import DecisionEvent, LabRun, RunStep
from precheck.core.schema.scenario import ScenarioStep
from precheck.core.settings import EXAMPLES_DIR
from precheck.core.testing import noul
from precheck.lab.agent.runner import judge, run_llm, run_scenario
from precheck.mcp_proxy.testing import Lab

SCENARIOS = EXAMPLES_DIR / "scenarios"


@dataclass
class FakeLabApi:
    lab: Lab
    runs: dict[str, LabRun] = field(default_factory=dict)
    steps: list[RunStep] = field(default_factory=list)
    extra_calls: list[dict[str, Any]] = field(default_factory=list)

    async def put_run(self, run: LabRun) -> None:
        self.runs[run.id] = run.model_copy(deep=True)

    async def put_step(self, run_id: str, step: RunStep) -> None:
        self.steps.append(step)

    async def tool_calls(self, session: str) -> list[dict[str, Any]]:
        return [
            {"tool": r.tool, "args": r.args} for r in self.lab.tools_log.records
        ] + self.extra_calls

    async def step_decisions(
        self, session: str, step: int, wait_s: float = 3.0
    ) -> list[DecisionEvent]:
        return [e for e in self.lab.control.decisions if e.session == session and e.step == step]


async def test_scripted_happy_refund_passes(lab: Lab) -> None:
    api = FakeLabApi(lab)
    run = await run_scenario(get_scenario(SCENARIOS, "happy-refund"), lab.proxy, api)  # type: ignore[arg-type]
    assert run.status == "passed", [s.mismatches for s in run.steps]
    assert [s.tool for s in run.steps] == ["lookup_order", "issue_refund"]
    assert all(s.reached_tool and s.verdict.value == "allow" for s in run.steps)  # type: ignore[union-attr]
    assert run.steps[1].decisions and run.steps[1].decisions[0].tool == "issue_refund"
    assert api.runs[run.id].status == "passed" and len(api.steps) == 2


async def test_scripted_records_blocked_steps_and_continues(lab: Lab) -> None:
    lab.jev.answers["different_method"] = noul(0.97)
    run = await run_scenario(get_scenario(SCENARIOS, "new-card-refund"), lab.proxy, FakeLabApi(lab))  # type: ignore[arg-type]
    assert run.status == "passed"
    refund = run.steps[1]
    assert refund.verdict.value == "deny" and refund.reached_tool is False  # type: ignore[union-attr]
    assert "refund-different-payment-method" in refund.message


async def test_wrong_expectation_fails_with_clear_diff(lab: Lab) -> None:
    scenario = get_scenario(SCENARIOS, "off-purpose-shell")
    assert scenario is not None
    wrong = scenario.model_copy(
        update={
            "steps": [
                ScenarioStep(
                    tool="run_shell",
                    args={"command": "top"},
                    reason="load",
                    expected_verdict="allow",
                    expect_reached_tool=True,
                )
            ]
        }
    )
    run = await run_scenario(wrong, lab.proxy, FakeLabApi(lab))
    assert run.status == "failed"
    assert run.steps[0].mismatches == [
        "verdict deny != expected allow",
        "reached_tool False != expected True",
    ]


async def test_reached_tool_mismatch_is_a_failure(lab: Lab) -> None:
    # Simulate a gate bypass: the proxy said deny but the tools log shows the call.
    api = FakeLabApi(lab, extra_calls=[{"tool": "run_shell", "args": {"command": "top -b -n 1"}}])

    async def leaky_calls(session: str) -> list[dict[str, Any]]:
        leaky_calls.n += 1  # type: ignore[attr-defined]
        return [] if leaky_calls.n == 1 else api.extra_calls  # type: ignore[attr-defined]

    leaky_calls.n = 0  # type: ignore[attr-defined]
    api.tool_calls = leaky_calls  # type: ignore[method-assign]
    run = await run_scenario(get_scenario(SCENARIOS, "off-purpose-shell"), lab.proxy, api)  # type: ignore[arg-type]
    assert run.status == "failed"
    assert run.steps[0].mismatches == ["reached_tool True != expected False"]


def test_judge_result_verdict() -> None:
    expected = ScenarioStep(
        tool="fetch_web_page",
        args={},
        reason="r",
        expected_verdict="allow",
        expect_reached_tool=True,
        expected_result_verdict="deny",
    )
    step = RunStep(
        index=1, tool="fetch_web_page", verdict="allow", result_verdict="allow", reached_tool=True
    )
    judged = judge(step, expected)
    assert not judged.passed and judged.mismatches == ["result verdict allow != expected deny"]


def test_all_scenarios_load() -> None:
    assert len(load_scenarios(SCENARIOS)) == 9
    assert get_scenario(SCENARIOS, "../etc") is None


@dataclass
class ScriptedLLM:
    responses: list[dict[str, Any]]
    model: str = "fake-claude"
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def create(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.requests.append(
            {"system": system, "messages": [dict(m) for m in messages], "tools": tools}
        )
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def tool_use(i: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "tool_use", "id": f"tu{i}", "name": name, "input": args}],
        "stop_reason": "tool_use",
    }


async def test_llm_loop_feeds_denies_back_and_stops(lab: Lab) -> None:
    llm = ScriptedLLM(
        [
            tool_use(1, "run_shell", {"command": "ls", "reason": "look around the server"}),
            tool_use(
                2,
                "lookup_order",
                {"order_id": "1234", "reason": "check the order the user asked about"},
            ),
            {
                "content": [
                    {"type": "text", "text": "I can't run shell commands; your order is delivered."}
                ],
                "stop_reason": "end_turn",
            },
        ]
    )
    api = FakeLabApi(lab)
    run = await run_llm("Where is order 1234?", "support-bot", "Support", llm, lab.proxy, api)  # type: ignore[arg-type]
    assert run.status == "completed" and run.final_text.startswith("I can't run shell")  # type: ignore[union-attr]
    assert [(s.tool, s.verdict.value, s.reason) for s in run.steps] == [  # type: ignore[union-attr]
        ("run_shell", "deny", "look around the server"),
        ("lookup_order", "allow", "check the order the user asked about"),
    ]
    # The deny was fed back to the model as an error tool_result.
    fed_back = llm.requests[1]["messages"][-1]["content"][0]
    assert fed_back["is_error"] is True and "Blocked by precheck" in fed_back["content"]
    # Tools offered to the model are the proxy's, with the injected reason.
    assert all("reason" in t["input_schema"]["required"] for t in llm.requests[0]["tools"])
    assert "support-bot" in llm.requests[0]["system"]


async def test_llm_loop_stops_at_max_turns(lab: Lab) -> None:
    llm = ScriptedLLM([tool_use(1, "lookup_order", {"order_id": "1234", "reason": "again"})])
    run = await run_llm("loop", "support-bot", None, llm, lab.proxy, FakeLabApi(lab), max_turns=3)  # type: ignore[arg-type]
    assert len(run.steps) == 3 and run.final_text == "(stopped after 3 turns)"


async def test_llm_errors_are_recorded(lab: Lab) -> None:
    class Broken(ScriptedLLM):
        async def create(self, **kw: Any) -> dict[str, Any]:
            raise RuntimeError("LLM mode is not configured: set ANTHROPIC_API_KEY")

    run = await run_llm("x", "support-bot", None, Broken([]), lab.proxy, FakeLabApi(lab))  # type: ignore[arg-type]
    assert run.status == "error" and "not configured" in (run.error or "")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Blocked by precheck (deny): x", ("deny", None)),
        ("Held for human approval (escalation e): x", ("escalate", None)),
        ("The result of fetch_web_page was withheld by precheck (deny): x", ("allow", "deny")),
        ("order nope not found", ("allow", None)),
    ],
)
def test_classify(text: str, expected: tuple[str, str | None]) -> None:
    from mcp.types import CallToolResult, TextContent

    from precheck.lab.agent.classify import classify

    v, rv = classify(CallToolResult(content=[TextContent(type="text", text=text)], is_error=True))
    assert (v.value, rv.value if rv else None) == expected


async def test_retry_step_uses_approval_in_same_session(lab: Lab) -> None:
    from precheck.lab.agent.runner import retry_step

    api = FakeLabApi(lab)
    run = await run_scenario(get_scenario(SCENARIOS, "large-refund"), lab.proxy, api)  # type: ignore[arg-type]
    assert run.steps[1].verdict.value == "escalate"  # type: ignore[union-attr]
    [esc_id] = lab.control.escalations
    lab.control.approve(esc_id)
    await lab.proxy.poll_approvals()
    retried = await retry_step(run, 2, lab.proxy, api)  # type: ignore[arg-type]
    assert retried.index == 3 and retried.verdict.value == "allow" and retried.reached_tool  # type: ignore[union-attr]
    assert retried.passed is None  # no expectation for an ad-hoc retry
    again = await retry_step(run, 2, lab.proxy, api)  # type: ignore[arg-type]
    assert again.verdict.value == "escalate"  # type: ignore[union-attr]
