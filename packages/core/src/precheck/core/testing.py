"""Test doubles and builders for code that uses the engine (FakeJev, rules, requests)."""

from dataclasses import dataclass, field
from typing import Any

from precheck.core.engine import EngineRule
from precheck.core.jev import JevResponse
from precheck.core.schema import CheckRequest, Gate, JevQuestion, JevUsage, RuleBody


@dataclass
class FakeJev:
    """Answers by question id suffix (`<rule>__<qid>` -> answers[qid] or answers[full id])."""

    answers: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail_with: Exception | None = None
    # Optional per-model answers (for Jev upgrade checks); falls back to `answers`.
    by_model: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = "jev-1.13.0"

    async def evaluate(
        self, state: Any, questions: dict[str, JevQuestion], model: str = "jev-latest"
    ) -> JevResponse:
        self.calls.append({"state": state, "questions": dict(questions), "model": model})
        if self.fail_with is not None:
            raise self.fail_with
        answers = self.by_model.get(model, self.answers)
        out = {}
        for nid in questions:
            key = nid if nid in answers else nid.split("__", 1)[1]
            if key in answers:
                out[nid] = answers[key]
        return JevResponse(
            resolved_model=model if model in self.by_model else self.model,
            answers=out,
            usage=JevUsage(input_tokens=100 * len(questions), output_tokens=1),
        )

    async def resolve_model(self, model: str = "jev-latest") -> str:
        return self.model


def noul(p: float) -> dict[str, Any]:
    return {"type": "noul", "noul": p}


def req(**over: Any) -> CheckRequest:
    base: dict[str, Any] = {
        "gate": "tool_call",
        "agent": {"id": "bot", "purpose": "support"},
        "context": {"user_goal": "refund order 1"},
        "history": [{"tool": "lookup_order", "args": {"id": "1"}, "result_summary": "Visa"}],
        "request": {"kind": "tool_call", "tool": "issue_refund", "args": {"amount": 100}},
        "reason": "customer asked",
    }
    base.update(over)
    return CheckRequest.model_validate({k: v for k, v in base.items() if v is not None})


def jev_body(
    *,
    qid: str = "q",
    bands: tuple[float, float] = (0.4, 0.7),
    template: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "jev": {
            "state_template": template or ["request"],
            "questions": {qid: {"type": "noul", "instructions": "Is it bad?"}},
            "outcomes": {
                qid: {"type": "noul", "bands": {"escalate_at": bands[0], "deny_at": bands[1]}}
            },
        },
        **extra,
    }


def det_body(pred: dict[str, Any], verdict: str, **extra: Any) -> dict[str, Any]:
    return {"deterministic": {"predicate": pred, "verdict_when_true": verdict}, **extra}


def rule(rid: str, body: dict[str, Any], gate: str = "tool_call", version: int = 1) -> EngineRule:
    return EngineRule(id=rid, gate=Gate(gate), body=RuleBody.model_validate(body), version=version)


GT_500 = {"op": "gt", "path": "request.args.amount", "value": 500}
IS_REFUND = {"op": "eq", "path": "request.tool", "value": "issue_refund"}


def noul_rule(**jev_overrides: Any) -> dict[str, Any]:
    """A minimal valid RuleBody dict with one noul question."""
    jev: dict[str, Any] = {
        "model": "jev-latest",
        "state_template": ["request"],
        "questions": {"risky": {"type": "noul", "instructions": "Is this risky?"}},
        "outcomes": {"risky": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}}},
    }
    jev.update(jev_overrides)
    return {"jev": jev}
