"""Translation service: runs the translator and persists business cases."""

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from precheck.authoring.errors import NotFoundError
from precheck.db.models import BusinessCase, RuleRow, RuleVersionRow
from precheck.schema import RuleBody
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
