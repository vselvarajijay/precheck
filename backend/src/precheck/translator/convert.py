"""Draft -> real contracts (RuleSpec, TestCaseSpec). Every problem is reported with a path
so it can be fed back to the LLM in a repair round."""

import json
from typing import Any

from pydantic import ValidationError

from precheck.schema import CheckRequest, RuleSpec, TestCaseSpec
from precheck.translator.draft import Condition, RuleDraft, TestDraft


def _errors(prefix: str, e: ValidationError) -> list[str]:
    return [f"{prefix}.{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]


def condition_to_predicate(c: Condition) -> dict[str, Any]:
    match c.op:
        case "exists" | "missing":
            return {"op": c.op, "path": c.path}
        case "eq" | "ne":
            value = c.value_number if c.value_number is not None else c.value_text
            return {"op": c.op, "path": c.path, "value": value}
        case "gt" | "gte" | "lt" | "lte":
            return {"op": c.op, "path": c.path, "value": c.value_number}
        case "in" | "not_in":
            return {"op": c.op, "path": c.path, "values": c.values}
        case "regex":
            return {"op": "regex", "path": c.path, "pattern": c.value_text}
        case "min_len":
            n = c.value_number
            return {"op": "min_len", "path": c.path, "value": int(n) if n is not None else None}
        case "domain_in" | "domain_not_in":
            return {"op": c.op, "path": c.path, "domains": c.domains}
    raise AssertionError(c.op)  # pragma: no cover


def _tools_selector(tools: list[str]) -> dict[str, Any] | None:
    tools = [t for t in dict.fromkeys(t.strip() for t in tools) if t]
    if not tools:
        return None
    if len(tools) == 1:
        return {"op": "eq", "path": "request.tool", "value": tools[0]}
    return {"op": "in", "path": "request.tool", "values": tools}


def rule_body_dict(d: RuleDraft, jev_model: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "requires": d.requires,
        "on_missing": d.on_missing,
        "severity": d.severity,
    }
    if (sel := _tools_selector(d.applies_to_tools)) is not None:
        body["applies_when"] = sel
    if d.on_error:
        body["on_error"] = d.on_error
    if d.deterministic:
        preds = [condition_to_predicate(c) for c in d.deterministic.conditions]
        pred: dict[str, Any] = (
            preds[0] if len(preds) == 1 else {"op": d.deterministic.combine, "predicates": preds}
        )
        if d.deterministic.negate:
            pred = {"op": "not", "predicate": pred}
        body["deterministic"] = {
            "predicate": pred,
            "verdict_when_true": d.deterministic.verdict_when_true,
        }
    if d.jev:
        questions: dict[str, Any] = {}
        outcomes: dict[str, Any] = {}
        for q in d.jev.questions:
            if q.type == "noul":
                question: dict[str, Any] = {"type": "noul", "instructions": q.instructions}
                if q.criteria_true and q.criteria_false:
                    question["criteria"] = {"true": q.criteria_true, "false": q.criteria_false}
                outcome: dict[str, Any] = {
                    "type": "noul",
                    "bands": {"escalate_at": q.escalate_at, "deny_at": q.deny_at},
                    "direction": "low_is_bad" if q.bad_answer == "false" else "high_is_bad",
                }
            elif q.type == "choice":
                question = {
                    "type": "choice",
                    "instructions": q.instructions,
                    "criteria": {o.name: o.description for o in q.options},
                }
                outcome = {
                    "type": "choice",
                    "map": {o.name: o.verdict for o in q.options},
                    "min_confidence": q.min_confidence,
                }
            else:
                question = {"type": "score", "instructions": q.instructions, "criteria": q.levels}
                outcome = {
                    "type": "score",
                    "bands": {"escalate_at": q.escalate_at, "deny_at": q.deny_at},
                    "min_confidence": q.min_confidence,
                }
            questions[q.id] = question
            outcomes[q.id] = outcome
        body["jev"] = {
            "model": jev_model,
            "state_template": d.jev.state_template,
            "questions": questions,
            "outcomes": outcomes,
        }
    return body


def convert_rule(
    d: RuleDraft, index: int, jev_model: str = "jev-latest"
) -> tuple[RuleSpec | None, list[str]]:
    prefix = f"rules[{index}] ({d.id})"
    try:
        spec = RuleSpec.model_validate(
            {
                "id": d.id,
                "name": d.name,
                "gate": d.gate,
                "source_text": d.source_text,
                "explanation": d.explanation,
                "body": rule_body_dict(d, jev_model),
            }
        )
    except ValidationError as e:
        return None, _errors(prefix, e)
    return spec, []


def _json_object(text: str, where: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError as e:
        errors.append(f"{where}: invalid JSON ({e.msg})")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{where}: must be a JSON object")
        return {}
    return value


def convert_test(
    t: TestDraft, index: int, rule: RuleSpec, agent_purpose: str | None
) -> tuple[TestCaseSpec | None, list[str]]:
    prefix = f"tests[{index}] ({t.name})"
    errors: list[str] = []
    history = [
        {
            "tool": h.tool,
            "args": _json_object(h.args_json, f"{prefix}.history[{i}].args_json", errors),
            "result_summary": h.result_summary or None,
        }
        for i, h in enumerate(t.history)
    ]
    request: dict[str, Any]
    if t.tool:
        request = {
            "kind": "tool_call",
            "tool": t.tool,
            "args": _json_object(t.args_json, f"{prefix}.args_json", errors),
        }
    elif t.url:
        request = {"kind": "external_call", "method": "POST", "url": t.url}
    else:
        request = {"kind": "content", "text": t.text or ""}
    data: dict[str, Any] = {
        "gate": rule.gate,
        "agent": {"id": "agent", "purpose": agent_purpose} if agent_purpose else None,
        "context": {"user_goal": t.user_goal} if t.user_goal else None,
        "history": history or None,
        "request": request,
        "reason": t.reason,
    }
    if errors:
        return None, errors
    try:
        cr = CheckRequest.model_validate(data)
        return TestCaseSpec(
            name=t.name, check_request=cr, expected_verdict=t.expected_verdict, origin="generated"
        ), []
    except ValidationError as e:
        return None, _errors(prefix, e)
