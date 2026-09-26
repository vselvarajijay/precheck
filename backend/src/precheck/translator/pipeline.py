"""Translator pipeline: business case -> validated draft rules, clarifications and tests.

One structured Claude call covers decompose + classify + generate + tests (the draft
schema makes each step an explicit field). Then, in code: convert to our contracts,
validate, repair (feed errors back, at most 2 rounds), enforce routing/quality lints.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel, Field, ValidationError

from precheck import __version__
from precheck.schema import Gate, RuleSpec, TestCaseSpec
from precheck.translator.convert import NotRepresentable, convert_rule, convert_test, spec_to_draft
from precheck.translator.draft import Clarification, PlanDraft, Requirement, RulesDraft, TestsDraft
from precheck.translator.lints import ExistingRule, TranslationWarning, lint_routing, lint_rule
from precheck.translator.llm import JsonLLM, LLMUsage

PROMPTS = Path(__file__).parent / "prompts"
PROMPT_NAME = "translate_v1"
MAX_REPAIR_ROUNDS = 2


@lru_cache
def load_prompt(name: str = PROMPT_NAME) -> tuple[str, str]:
    """(text, version) — the version pins the exact prompt bytes used."""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return text, f"{name}+{hashlib.sha256(text.encode()).hexdigest()[:8]}"


@lru_cache
def schema_for(step: str) -> dict[str, Any]:
    models: dict[str, type[BaseModel]] = {
        "plan": PlanDraft,
        "rules": RulesDraft,
        "tests": TestsDraft,
    }
    return anthropic.transform_schema(models[step])


class TranslateInput(BaseModel):
    text: str = Field(min_length=1, max_length=8000, description="The business case, in prose")
    gate_hint: Gate | None = None
    tools: list[str] = Field(default_factory=list, description="Tool catalog the agent has")
    agent_purpose: str | None = None
    domains: list[str] = Field(default_factory=list, description="Our own / allowlisted domains")
    answers: dict[str, str] = Field(default_factory=dict, description="Clarification id -> answer")


class Provenance(BaseModel):
    translator_model: str
    prompt_version: str
    code_version: str = __version__


class TranslatedRule(BaseModel):
    spec: RuleSpec
    warnings: list[TranslationWarning] = Field(default_factory=list)


class TranslatedTest(BaseModel):
    rule_id: str
    kind: str
    test: TestCaseSpec


class TranslationResult(BaseModel):
    status: str = Field(description="translated | needs_clarification | failed")
    requirements: list[Requirement] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)
    rules: list[TranslatedRule] = Field(default_factory=list)
    tests: list[TranslatedTest] = Field(default_factory=list)
    warnings: list[TranslationWarning] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list, description="Problems left after repair")
    repair_rounds: int = 0
    provenance: Provenance
    usage: LLMUsage = Field(default_factory=LLMUsage)
    cost_usd: float = 0.0


def user_message(inp: TranslateInput) -> str:
    parts = [f"Business case:\n{inp.text.strip()}"]
    if inp.gate_hint:
        parts.append(f"Gate hint: {inp.gate_hint.value}")
    if inp.tools:
        parts.append("Tool catalog: " + ", ".join(inp.tools))
    if inp.agent_purpose:
        parts.append(f"Agent purpose: {inp.agent_purpose}")
    if inp.domains:
        parts.append("Our own / allowlisted domains: " + ", ".join(inp.domains))
    if inp.answers:
        answered = "\n".join(f"- {k}: {v}" for k, v in sorted(inp.answers.items()))
        parts.append(
            "The author answered these clarifications; apply them and do not ask again:\n"
            + answered
        )
    return "\n\n".join(parts)


def semantic_problems(spec: RuleSpec) -> list[str]:
    """Valid-but-wrong rules the schema can't catch; fed back to the LLM for repair."""
    body = spec.body
    problems = []
    if body.deterministic and body.deterministic.verdict_when_true == "allow" and not body.jev:
        problems.append(
            "deterministic.verdict_when_true is allow but the rule has no Jev check, so the rule "
            "allows either way and has no effect; describe the violation (use negate if needed) "
            "with deny or escalate"
        )
    return problems


def plan_message(inp: TranslateInput) -> str:
    step = "Step 1 of 3 (plan): decompose and route; ask only blocking clarifications."
    return f"{user_message(inp)}\n\n{step}"


def rules_message(inp: TranslateInput, plan: PlanDraft) -> str:
    plan_json = plan.model_dump_json(include={"requirements", "clarifications"})
    return (
        f"{user_message(inp)}\n\nPlan from step 1:\n{plan_json}\n\n"
        "Step 2 of 3 (rules): write the rules for these requirements."
    )


def tests_message(inp: TranslateInput, rules_json: str) -> str:
    return (
        f"{user_message(inp)}\n\nRules from step 2:\n{rules_json}\n\n"
        "Step 3 of 3 (tests): write 4 tests for every rule (positive, negative, boundary, "
        "adversarial)."
    )


def repair_message(errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors[:40])
    return (
        "Your rules failed validation:\n"
        f"{listed}\n\n"
        "Fix every problem and return the complete corrected list of rules."
    )


Progress = Callable[[str], Awaitable[None]]


class RefineResult(BaseModel):
    rule: TranslatedRule | None = None
    errors: list[str] = Field(default_factory=list)
    repair_rounds: int = 0
    provenance: Provenance
    usage: LLMUsage = Field(default_factory=LLMUsage)
    cost_usd: float = 0.0


def refine_message(spec: RuleSpec, instruction: str) -> str:
    return (
        f"Rule to refine (JSON):\n{json.dumps(spec_to_draft(spec))}\n\n"
        f"Change requested by the author:\n{instruction.strip()}\n\n"
        "Return the refined rule as the only item of `rules`. Keep its id and source_text; "
        "change only what the request needs, and update the explanation to match."
    )


class Translator:
    def __init__(
        self,
        llm: JsonLLM,
        *,
        existing: list[ExistingRule] | None = None,
        generate_tests: bool = True,
        progress: Progress | None = None,
    ) -> None:
        self.llm = llm
        self.existing = existing or []
        self.generate_tests = generate_tests
        self.progress = progress
        self.usage = LLMUsage()

    async def _emit(self, stage: str) -> None:
        if self.progress is not None:
            await self.progress(stage)

    async def refine(self, spec: RuleSpec, instruction: str) -> RefineResult:
        """One rule + a plain-language change request -> the refined rule (rules step)."""
        self.usage = LLMUsage()
        _, prompt_version = load_prompt()
        result = RefineResult(
            provenance=Provenance(translator_model=self.llm.model, prompt_version=prompt_version)
        )
        try:
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": refine_message(spec, instruction)}
            ]
        except NotRepresentable as e:
            result.errors = [str(e)]
            return result
        try:
            rounds = 0
            while True:
                text = await self._step("rules", messages)
                specs, errors = self._convert_rules(text)
                if len(specs) != 1:
                    errors.append(f"expected exactly one refined rule, got {len(specs)}")
                if not errors or rounds >= MAX_REPAIR_ROUNDS:
                    break
                rounds += 1
                messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": repair_message(errors)},
                ]
            result.repair_rounds = rounds
            result.errors = errors
            if specs:
                refined = specs[0]
                result.rule = TranslatedRule(
                    spec=refined, warnings=lint_rule(refined, self.existing)
                )
        finally:
            result.usage = self.usage
            result.cost_usd = round(self.usage.cost_usd(self.llm.model), 6)
        return result

    async def _step(self, step: str, messages: list[dict[str, Any]]) -> str:
        await self._emit(step)
        system, _ = load_prompt()
        resp = await self.llm.complete_json(
            system=system, messages=messages, schema=schema_for(step)
        )
        self.usage = self.usage + resp.usage
        return resp.text

    async def translate(self, inp: TranslateInput) -> TranslationResult:
        self.usage = LLMUsage()
        _, prompt_version = load_prompt()
        result = TranslationResult(
            status="failed",
            provenance=Provenance(translator_model=self.llm.model, prompt_version=prompt_version),
        )
        try:
            await self._run(inp, result)
        finally:
            result.usage = self.usage
            result.cost_usd = round(self.usage.cost_usd(self.llm.model), 6)
        return result

    async def _run(self, inp: TranslateInput, result: TranslationResult) -> None:
        # Step 1: plan (decompose + classify + clarify).
        text = await self._step("plan", [{"role": "user", "content": plan_message(inp)}])
        try:
            plan = PlanDraft.model_validate_json(text)
        except ValidationError as e:
            result.errors = [f"plan did not match the schema: {e}"]
            return
        result.requirements = plan.requirements
        result.clarifications = plan.clarifications
        if plan.status == "needs_clarification" and plan.clarifications:
            result.status = "needs_clarification"
            return

        # Step 2: rules, validated and repaired (at most MAX_REPAIR_ROUNDS extra calls).
        messages: list[dict[str, Any]] = [{"role": "user", "content": rules_message(inp, plan)}]
        rounds = 0
        while True:
            text = await self._step("rules", messages)
            await self._emit("validating")
            specs, errors = self._convert_rules(text)
            if not errors or rounds >= MAX_REPAIR_ROUNDS:
                break
            rounds += 1
            await self._emit("repairing")
            messages = [
                *messages,
                {"role": "assistant", "content": text},
                {"role": "user", "content": repair_message(errors)},
            ]
        result.repair_rounds = rounds
        result.errors = errors
        result.rules = [TranslatedRule(spec=s, warnings=lint_rule(s, self.existing)) for s in specs]
        result.warnings = lint_routing(plan.requirements, specs)
        if not specs:
            return
        result.status = "translated"
        if not self.generate_tests:
            return

        # Step 3: tests for the valid rules. Invalid tests are dropped with a warning.
        rules_json = json.dumps(
            [s.model_dump(mode="json", by_alias=True, exclude_none=True) for s in specs]
        )
        text = await self._step(
            "tests", [{"role": "user", "content": tests_message(inp, rules_json)}]
        )
        result.tests, test_errors = self._convert_tests(text, {s.id: s for s in specs}, inp)
        result.warnings += [
            TranslationWarning(rule_id=None, code="invalid_test", message=e) for e in test_errors
        ]

    @staticmethod
    def _convert_rules(text: str) -> tuple[list[RuleSpec], list[str]]:
        try:
            draft = RulesDraft.model_validate_json(text)
        except ValidationError as e:
            return [], [f"rules did not match the schema: {e}"]
        if not draft.rules:
            return [], ["no rules were produced"]
        errors: list[str] = []
        specs: dict[str, RuleSpec] = {}
        for i, rd in enumerate(draft.rules):
            spec, errs = convert_rule(rd, i)
            errors.extend(errs)
            if spec is not None:
                if spec.id in specs:
                    errors.append(f"rules[{i}]: duplicate rule id {spec.id!r}")
                errors.extend(f"rules[{i}] ({spec.id}): {p}" for p in semantic_problems(spec))
                specs[spec.id] = spec
        return list(specs.values()), errors

    @staticmethod
    def _convert_tests(
        text: str, rules: dict[str, RuleSpec], inp: TranslateInput
    ) -> tuple[list[TranslatedTest], list[str]]:
        try:
            draft = TestsDraft.model_validate_json(text)
        except ValidationError as e:
            return [], [f"tests did not match the schema: {e}"]
        tests: list[TranslatedTest] = []
        errors: list[str] = []
        for i, td in enumerate(draft.tests):
            rule = rules.get(td.rule_id)
            if rule is None:
                errors.append(f"tests[{i}] ({td.name}): unknown rule_id {td.rule_id!r}")
                continue
            tc, errs = convert_test(td, i, rule, inp.agent_purpose)
            errors.extend(errs)
            if tc is not None:
                tests.append(TranslatedTest(rule_id=rule.id, kind=td.kind, test=tc))
        return tests, errors
