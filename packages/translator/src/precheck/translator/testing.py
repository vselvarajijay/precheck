"""Test doubles for code that uses the translator: a scripted LLM and draft builders."""

import json
from dataclasses import dataclass, field
from typing import Any

from precheck.translator.llm import LLMResponse, LLMUsage

STEP_BY_TITLE = {"PlanDraft": "plan", "RulesDraft": "rules", "TestsDraft": "tests"}


@dataclass
class FakeLLM:
    """Scripted LLM: each step pops its next response (dict -> JSON text)."""

    script: dict[str, list[Any]]
    model: str = "fake-claude"
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> LLMResponse:
        step = STEP_BY_TITLE[schema["title"]]
        self.calls.append({"step": step, "messages": messages, "system": system})
        queue = self.script[step]
        payload = queue.pop(0) if len(queue) > 1 else queue[0]
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return LLMResponse(
            text=text,
            model=self.model,
            stop_reason="end_turn",
            usage=LLMUsage(input_tokens=1000, output_tokens=500),
        )

    def steps(self) -> list[str]:
        return [c["step"] for c in self.calls]


def plan(status: str = "ok", clarifications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "requirements": [
            {
                "source_sentence": "Refunds over $500 need a manager.",
                "requirement": "big refunds need a human",
                "routing": "deterministic",
                "routing_reason": "numeric threshold",
            },
            {
                "source_sentence": "Never refund to a different card.",
                "requirement": "same card only",
                "routing": "judgment",
                "routing_reason": "interpretation",
            },
        ],
        "clarifications": clarifications or [],
    }


def det_rule(**over: Any) -> dict[str, Any]:
    rule = {
        "id": "refund-over-limit",
        "name": "Refund over limit",
        "gate": "tool_call",
        "source_text": "Refunds over $500 need a manager.",
        "explanation": "Big refunds wait for a human.",
        "severity": "medium",
        "applies_to_tools": ["issue_refund"],
        "requires": ["request.args.amount"],
        "on_missing": "escalate",
        "on_error": None,
        "jev": None,
        "deterministic": {
            "combine": "all",
            "negate": False,
            "verdict_when_true": "escalate",
            "conditions": [
                {
                    "path": "request.args.amount",
                    "op": "gt",
                    "value_text": None,
                    "value_number": 500,
                    "values": [],
                    "domains": [],
                }
            ],
        },
    }
    rule.update(over)
    return rule


def jev_rule(**over: Any) -> dict[str, Any]:
    rule = {
        "id": "refund-different-card",
        "name": "Refund to different card",
        "gate": "tool_call",
        "source_text": "Never refund to a different card.",
        "explanation": "Refunds go to the original card.",
        "severity": "high",
        "applies_to_tools": ["issue_refund"],
        "requires": ["history"],
        "on_missing": "escalate",
        "on_error": None,
        "deterministic": None,
        "jev": {
            "state_template": ["request", "history"],
            "questions": [
                {
                    "id": "different_method",
                    "type": "noul",
                    "instructions": (
                        "Does this refund go to a different payment method than the purchase used?"
                    ),
                    "criteria_true": (
                        "The destination names another card or account than the purchase"
                    ),
                    "criteria_false": "The destination is the same card or account as the purchase",
                    "bad_answer": "true",
                    "options": [],
                    "levels": [],
                    "escalate_at": 0.3,
                    "deny_at": 0.6,
                    "min_confidence": 0,
                }
            ],
        },
    }
    rule.update(over)
    return rule


def draft_test(rule_id: str = "refund-over-limit", **over: Any) -> dict[str, Any]:
    t: dict[str, Any] = {
        "rule_id": rule_id,
        "name": "big refund",
        "kind": "negative",
        "expected_verdict": "escalate",
        "user_goal": "refund order 1",
        "history": [],
        "tool": "issue_refund",
        "args_json": '{"order_id": "1", "amount": 900}',
        "url": None,
        "text": None,
        "reason": "damaged",
    }
    t.update(over)
    return t
