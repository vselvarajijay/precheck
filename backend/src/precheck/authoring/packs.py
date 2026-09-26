"""Load a RulePack into the database as draft rules (existing ids are skipped)."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from precheck.authoring.dto import RuleCreate
from precheck.authoring.rules import RuleService
from precheck.schema import RulePack


class PackLoadResult(BaseModel):
    created: list[str]
    skipped: list[str]


def load_pack(session: Session, pack: RulePack, *, created_by: str = "user") -> PackLoadResult:
    svc = RuleService(session)
    created: list[str] = []
    skipped: list[str] = []
    for spec in pack.rules:
        if svc.repo.exists(spec.id):
            skipped.append(spec.id)
            continue
        svc.create(
            RuleCreate(
                id=spec.id,
                name=spec.name,
                gate=spec.gate,
                body=spec.body,
                source_text=spec.source_text,
                explanation=spec.explanation,
            ),
            created_by=created_by,
        )
        created.append(spec.id)
    return PackLoadResult(created=created, skipped=skipped)
