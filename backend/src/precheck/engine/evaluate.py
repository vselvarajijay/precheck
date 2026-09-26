"""evaluate(rules, check_request, jev) -> Decision.

Semantics (considerations.md §4, decided in slices 01/03):
1. A rule participates only if its gate matches and `applies_when` holds.
2. Missing `requires` fields -> `on_missing` verdict for that rule.
3. Deterministic predicate true -> `verdict_when_true`, the rule's Jev check is skipped.
   False -> the Jev check decides, or allow if the rule has none.
4. If any rule is already `deny` before Jev, no Jev call is made (short-circuit).
5. Remaining Jev checks are batched (one call per (model, state) group, concurrently);
   each question maps through its outcome; a rule takes its strictest question verdict.
6. Jev failure -> rule `on_error`, else default: escalate for tool_call/egress, allow for
   ingress (flagged via `error`), never below escalate for high severity.
7. Final verdict: deny > escalate > allow over participating rules; if none produced a
   verdict, the gate default (allow unless configured).
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from precheck import __version__
from precheck.engine.outcomes import OutcomeError, map_answer
from precheck.jev import JevCall, JevError, JevResponse, build_calls, split_answers
from precheck.schema import (
    CheckRequest,
    Decision,
    DecisionVersions,
    Gate,
    JevCheck,
    JevQuestion,
    JevUsage,
    QuestionResult,
    RuleBody,
    RulePack,
    RuleResult,
    Severity,
    Verdict,
    evaluate_predicate,
    predicate_paths,
    resolve,
    strictest,
)
from precheck.schema.paths import MISSING

ENGINE_VERSION = __version__


class JevEvaluator(Protocol):
    async def evaluate(
        self, state: Any, questions: dict[str, JevQuestion], model: str = ...
    ) -> JevResponse: ...


@dataclass(frozen=True)
class EngineRule:
    """A rule version as the engine sees it."""

    id: str
    gate: Gate
    body: RuleBody
    version: int | None = None
    name: str | None = None


def rules_from_pack(pack: RulePack, version: int | None = 1) -> list[EngineRule]:
    return [
        EngineRule(id=r.id, gate=r.gate, body=r.body, version=version, name=r.name)
        for r in pack.rules
    ]


@dataclass
class EngineConfig:
    no_match: dict[Gate, Verdict] = field(
        default_factory=lambda: dict.fromkeys(Gate, Verdict.allow)
    )
    policy_version: str | None = None


def default_on_error(gate: Gate, severity: Severity) -> Verdict:
    if severity is Severity.high:
        return Verdict.escalate
    return Verdict.allow if gate is Gate.ingress else Verdict.escalate


def _on_error(rule: EngineRule) -> Verdict:
    return rule.body.on_error or default_on_error(rule.gate, rule.body.severity)


def _inputs(pred: Any, data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in predicate_paths(pred):
        v = resolve(data, p).value
        out[p] = None if v is MISSING else v
    return out


async def evaluate(
    rules: list[EngineRule],
    check_request: CheckRequest,
    jev: JevEvaluator | None,
    config: EngineConfig | None = None,
) -> Decision:
    started = time.perf_counter()
    config = config or EngineConfig()
    data = check_request.as_data()
    results: dict[str, RuleResult] = {}
    pending_jev: list[tuple[EngineRule, JevCheck]] = []

    for rule in rules:
        res = RuleResult(rule_id=rule.id, rule_version=rule.version, matched=False)
        results[rule.id] = res
        if rule.gate != check_request.gate:
            res.reason = f"gate is {rule.gate}, request is {check_request.gate}"
            continue
        body = rule.body
        if body.applies_when is not None and not evaluate_predicate(body.applies_when, data):
            res.reason = "applies_when is false"
            continue
        res.matched = True

        missing = [p for p in body.requires if resolve(data, p).missing]
        if missing:
            res.verdict, res.source, res.missing_fields = body.on_missing, "missing_fields", missing
            res.reason = f"missing required field(s): {', '.join(missing)}"
            continue

        if body.deterministic is not None:
            det = body.deterministic
            hit = evaluate_predicate(det.predicate, data)
            res.predicate_result = hit
            res.predicate_inputs = _inputs(det.predicate, data)
            if hit:
                res.verdict, res.source = det.verdict_when_true, "deterministic"
                res.reason = "deterministic check matched"
                continue
            if body.jev is None:
                res.verdict, res.source = Verdict.allow, "deterministic"
                res.reason = "deterministic check did not match"
                continue

        if body.jev is not None:
            pending_jev.append((rule, body.jev))

    usage = JevUsage()
    resolved_models: set[str] = set()
    denied_by = [r.rule_id for r in results.values() if r.verdict is Verdict.deny]
    if pending_jev and denied_by:
        for rule, _ in pending_jev:
            res = results[rule.id]
            res.source = "no_verdict"
            res.reason = f"Jev check skipped: already denied by {', '.join(denied_by)}"
    elif pending_jev:
        usage, resolved_models = await _run_jev(pending_jev, data, jev, results)

    participating = [r.verdict for r in results.values() if r.matched and r.verdict is not None]
    verdict = strictest(participating)
    gate_default = verdict is None
    if verdict is None:
        verdict = config.no_match[check_request.gate]

    return Decision(
        verdict=verdict,
        rule_results=list(results.values()),
        gate_default_applied=gate_default,
        versions=DecisionVersions(
            engine=ENGINE_VERSION,
            policy=config.policy_version,
            jev_model=",".join(sorted(resolved_models)) or None,
            rules={r.id: r.version for r in rules if results[r.id].matched and r.version},
        ),
        latency_ms=(time.perf_counter() - started) * 1000,
        usage=usage,
    )


async def _run_jev(
    pending: list[tuple[EngineRule, JevCheck]],
    data: dict[str, Any],
    jev: JevEvaluator | None,
    results: dict[str, RuleResult],
) -> tuple[JevUsage, set[str]]:
    by_id = {rule.id: rule for rule, _ in pending}

    def fail(rule_ids: list[str], message: str) -> None:
        for rid in rule_ids:
            res = results[rid]
            res.verdict, res.source, res.error = _on_error(by_id[rid]), "error", message
            res.reason = f"Jev error -> on_error {res.verdict}"

    if jev is None:
        fail(list(by_id), "no Jev client configured")
        return JevUsage(), set()

    # Build calls; if one rule's state is too large, isolate it rather than failing all.
    calls: list[JevCall] = []
    try:
        calls = build_calls([(r.id, c) for r, c in pending], data)
    except JevError:
        for rule, check in pending:
            try:
                calls.extend(build_calls([(rule.id, check)], data))
            except JevError as e:
                fail([rule.id], str(e))

    responses = await asyncio.gather(
        *(jev.evaluate(c.state, c.questions, c.model) for c in calls), return_exceptions=True
    )
    usage = JevUsage()
    models: set[str] = set()
    for call, resp in zip(calls, responses, strict=True):
        if isinstance(resp, BaseException):
            if not isinstance(resp, JevError | TimeoutError):
                raise resp
            fail(call.rule_ids, f"{type(resp).__name__}: {resp}")
            continue
        usage = usage + resp.usage
        models.add(resp.resolved_model)
        answers = split_answers(call, resp)
        for rid in call.rule_ids:
            _apply_answers(by_id[rid], answers.get(rid, {}), results[rid], fail)
    return usage, models


def _apply_answers(rule: EngineRule, answers: dict[str, Any], res: RuleResult, fail: Any) -> None:
    check = rule.body.jev
    assert check is not None
    mapped: dict[str, QuestionResult] = {}
    for qid, outcome in check.outcomes.items():
        if qid not in answers:
            fail([rule.id], f"Jev returned no answer for question {qid!r}")
            return
        try:
            mapped[qid] = map_answer(outcome, answers[qid])
        except OutcomeError as e:
            fail([rule.id], f"{qid}: {e}")
            return
    res.jev = mapped
    res.verdict = strictest([q.verdict for q in mapped.values()])
    res.source = "jev"
    res.reason = "; ".join(f"{qid}: {q.band}" for qid, q in mapped.items())
