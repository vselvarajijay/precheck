"""Translation service: runs the translator and persists business cases."""

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from precheck.authoring.dto import Provenance as RuleProvenance
from precheck.authoring.dto import RuleCreate
from precheck.authoring.errors import NotFoundError
from precheck.authoring.rules import RuleService
from precheck.authoring.test_cases import TestCaseCreate, TestCaseService
from precheck.db.models import BusinessCase, RuleRow, RuleVersionRow
from precheck.schema import RuleBody, RuleSpec, TestCaseSpec
from precheck.schema.predicate import selector_tools
from precheck.translator.lints import ExistingRule
from precheck.translator.pipeline import TranslateInput, TranslationResult


class TranslateResponse(BaseModel):
    business_case_id: str
    result: TranslationResult


class ClarificationAnswers(BaseModel):
    answers: dict[str, str] = Field(min_length=1, description="Clarification id -> answer")


def existing_rules(session: Session) -> list[ExistingRule]:
    out = []
    for rule in session.query(RuleRow).filter(RuleRow.status != "archived"):
        version = session.get(RuleVersionRow, rule.current_version_id)
        if version is None:
            continue
        body = RuleBody.model_validate(version.body_json)
        out.append(
            ExistingRule(id=rule.id, gate=rule.gate, tools=selector_tools(body.applies_when))
        )
    return out


def create_case(
    session: Session, inp: TranslateInput, result: TranslationResult, created_by: str
) -> str:
    row = BusinessCase(
        id=str(uuid.uuid4()),
        text=inp.text,
        gate_hint=inp.gate_hint.value if inp.gate_hint else None,
        context_json=inp.model_dump(mode="json"),
        status=result.status,
        result_json=result.model_dump(mode="json", by_alias=True),
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    return row.id


def load_case_input(session: Session, case_id: str) -> TranslateInput:
    row = session.get(BusinessCase, case_id)
    if row is None:
        raise NotFoundError(f"business case {case_id!r} not found")
    return TranslateInput.model_validate(row.context_json)


def update_case(
    session: Session, case_id: str, inp: TranslateInput, result: TranslationResult
) -> None:
    row = session.get(BusinessCase, case_id)
    if row is None:
        raise NotFoundError(f"business case {case_id!r} not found")
    row.context_json = inp.model_dump(mode="json")
    row.status = result.status
    row.result_json = result.model_dump(mode="json", by_alias=True)
    session.flush()


def get_case(session: Session, case_id: str) -> TranslateResponse:
    row = session.get(BusinessCase, case_id)
    if row is None:
        raise NotFoundError(f"business case {case_id!r} not found")
    return TranslateResponse(
        business_case_id=row.id, result=TranslationResult.model_validate(row.result_json)
    )


class SaveTest(BaseModel):
    rule_id: str
    test: TestCaseSpec


class SaveTranslation(BaseModel):
    rules: list[RuleSpec] = Field(min_length=1, description="The (possibly edited) rules to save")
    tests: list[SaveTest] = Field(default_factory=list)


class SavedRule(BaseModel):
    requested_id: str
    id: str


class SaveResult(BaseModel):
    rules: list[SavedRule]
    tests_created: int


def save_translation(
    session: Session, case_id: str, data: SaveTranslation, created_by: str = "user"
) -> SaveResult:
    """Create every rule as a draft (ids that exist get a suffix) and its generated tests."""
    row = session.get(BusinessCase, case_id)
    if row is None:
        raise NotFoundError(f"business case {case_id!r} not found")
    prov = (row.result_json or {}).get("provenance") or {}
    provenance = RuleProvenance(
        translator_model=prov.get("translator_model"), prompt_version=prov.get("prompt_version")
    )
    rules = RuleService(session)
    saved: list[SavedRule] = []
    id_map: dict[str, str] = {}
    for spec in data.rules:
        rule_id = spec.id if not rules.repo.exists(spec.id) else rules._unique_id(spec.id)
        detail = rules.create(
            RuleCreate(
                id=rule_id,
                name=spec.name,
                gate=spec.gate,
                body=spec.body,
                source_text=spec.source_text,
                explanation=spec.explanation,
                provenance=provenance,
            ),
            created_by=created_by,
        )
        row_rule = rules.repo.get(detail.id)
        assert row_rule is not None
        row_rule.business_case_id = case_id
        id_map[spec.id] = detail.id
        saved.append(SavedRule(requested_id=spec.id, id=detail.id))
    tests = TestCaseService(session)
    created = 0
    for t in data.tests:
        if t.rule_id not in id_map:
            continue
        tests.create(
            TestCaseCreate(
                rule_id=id_map[t.rule_id],
                name=t.test.name,
                check_request=t.test.check_request,
                expected_verdict=t.test.expected_verdict,
                origin="generated",
            )
        )
        created += 1
    row.status = "saved"
    session.flush()
    return SaveResult(rules=saved, tests_created=created)
