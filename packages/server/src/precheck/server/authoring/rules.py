"""Rules service: create, version, publish (status) and archive rules.

Versions are immutable. An edit creates a new version unless nothing changed (same body
hash, source text and explanation). `current` is the latest version (what drafts
evaluate); `live` is the version enforcement uses, pinned when the rule is set live.
"""

import re
from typing import Any

from sqlalchemy.orm import Session

from precheck.core.schema import Gate, RuleBody, RuleVersion, content_hash
from precheck.core.schema.predicate import selector_tools
from precheck.core.schema.rule import live_problem_details
from precheck.server.authoring.dto import (
    Provenance,
    RuleCreate,
    RuleDetail,
    RuleListStatus,
    RuleSummary,
    RuleUpdate,
    RuleUpdateResult,
    VersionSummary,
)
from precheck.server.authoring.errors import (
    ConflictError,
    FieldProblem,
    LiveValidationError,
    NotFoundError,
)
from precheck.server.db.models import RuleRow, RuleVersionRow, utcnow
from precheck.server.db.repos import RuleRepo


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64].strip("-")
    return slug or "rule"


def to_rule_version(row: RuleVersionRow) -> RuleVersion:
    return RuleVersion(
        rule_id=row.rule_id,
        version=row.version,
        body=RuleBody.model_validate(row.body_json),
        source_text=row.source_text,
        explanation=row.explanation,
        jev_model=row.jev_model,
        translator_model=row.translator_model,
        prompt_version=row.prompt_version,
        content_hash=row.content_hash,
        created_at=row.created_at,
    )


class RuleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = RuleRepo(session)

    # --- queries ------------------------------------------------------------------------

    def list_rules(
        self,
        *,
        gate: Gate | None = None,
        status: RuleListStatus | None = None,
        q: str | None = None,
    ) -> list[RuleSummary]:
        statuses: list[str] | None
        if status is None:
            statuses = ["draft", "live"]  # archived hidden by default
        elif status == "all":
            statuses = None
        else:
            statuses = [status]
        rows = self.repo.search(gate=Gate(gate).value if gate else None, statuses=statuses, q=q)
        return [self._summary(r) for r in rows]

    def get(self, rule_id: str) -> RuleDetail:
        return self._detail(self._row(rule_id))

    def get_version(self, rule_id: str, version: int) -> RuleVersion:
        self._row(rule_id)
        row = self.repo.get_version(rule_id, version)
        if row is None:
            raise NotFoundError(f"rule {rule_id!r} has no version {version}")
        return to_rule_version(row)

    # --- commands -----------------------------------------------------------------------

    def create(self, data: RuleCreate, *, created_by: str = "user") -> RuleDetail:
        if data.id is not None:
            if self.repo.exists(data.id):
                raise ConflictError(f"rule {data.id!r} already exists")
            rule_id = data.id
        else:
            rule_id = self._unique_id(slugify(data.name))
        rule = self.repo.add(
            RuleRow(
                id=rule_id,
                name=data.name,
                gate=data.gate.value,
                status="draft",
                created_by=created_by,
            )
        )
        version = self._new_version(
            rule_id, 1, data.body, data.source_text, data.explanation, data.provenance
        )
        rule.current_version_id = version.id
        self.session.flush()
        return self._detail(rule)

    def update(self, rule_id: str, data: RuleUpdate) -> RuleUpdateResult:
        rule = self._row(rule_id)
        if rule.status == "archived":
            raise ConflictError(f"rule {rule_id!r} is archived; restore it to draft first")
        if data.name is not None:
            rule.name = data.name
        current = rule.current_version
        assert current is not None
        source_text = data.source_text if data.source_text is not None else current.source_text
        explanation = data.explanation if data.explanation is not None else current.explanation
        unchanged = (
            content_hash(data.body) == current.content_hash
            and source_text == current.source_text
            and explanation == current.explanation
        )
        if not unchanged:
            version = self._new_version(
                rule_id,
                self.repo.next_version(rule_id),
                data.body,
                source_text,
                explanation,
                data.provenance,
            )
            rule.current_version_id = version.id
        rule.updated_at = utcnow()
        self.session.flush()
        self.session.refresh(rule)
        return RuleUpdateResult(**self._detail(rule).model_dump(), created_version=not unchanged)

    def set_status(self, rule_id: str, status: str) -> RuleDetail:
        rule = self._row(rule_id)
        if status == "live":
            current = rule.current_version
            assert current is not None
            problems = live_problem_details(RuleBody.model_validate(current.body_json))
            if problems:
                raise LiveValidationError(
                    [FieldProblem(field=f"body.{f}", message=m) for f, m in problems]
                )
            rule.live_version_id = current.id
        else:
            rule.live_version_id = None
        rule.status = status
        rule.updated_at = utcnow()
        self.session.flush()
        self.session.refresh(rule)
        return self._detail(rule)

    def archive(self, rule_id: str) -> RuleDetail:
        return self.set_status(rule_id, "archived")

    # --- helpers ------------------------------------------------------------------------

    def _row(self, rule_id: str) -> RuleRow:
        row = self.repo.get(rule_id)
        if row is None:
            raise NotFoundError(f"rule {rule_id!r} not found")
        return row

    def _unique_id(self, base: str) -> str:
        candidate, n = base, 2
        while self.repo.exists(candidate):
            suffix = f"-{n}"
            candidate = base[: 64 - len(suffix)].rstrip("-") + suffix
            n += 1
        return candidate

    def _new_version(
        self,
        rule_id: str,
        version: int,
        body: RuleBody,
        source_text: str | None,
        explanation: str | None,
        provenance: Provenance | None,
    ) -> RuleVersionRow:
        return self.repo.add_version(
            RuleVersionRow(
                rule_id=rule_id,
                version=version,
                body_json=body.model_dump(mode="json", by_alias=True, exclude_none=True),
                source_text=source_text,
                explanation=explanation,
                jev_model=body.jev.model if body.jev else None,
                translator_model=provenance.translator_model if provenance else None,
                prompt_version=provenance.prompt_version if provenance else None,
                content_hash=content_hash(body),
            )
        )

    def _summary_fields(self, rule: RuleRow) -> dict[str, Any]:
        current = rule.current_version
        assert current is not None
        body = RuleBody.model_validate(current.body_json)
        return {
            "id": rule.id,
            "name": rule.name,
            "gate": rule.gate,
            "status": rule.status,
            "created_by": rule.created_by,
            "current_version": current.version,
            "live_version": rule.live_version.version if rule.live_version else None,
            "source_text": current.source_text,
            "severity": body.severity,
            "has_deterministic": body.deterministic is not None,
            "has_jev": body.jev is not None,
            "jev_model": body.jev.model if body.jev else None,
            "requires": list(body.requires),
            "applies_to_tools": selector_tools(body.applies_when),
            "updated_at": rule.updated_at,
        }

    def _summary(self, rule: RuleRow) -> RuleSummary:
        return RuleSummary(**self._summary_fields(rule))

    def _detail(self, rule: RuleRow) -> RuleDetail:
        assert rule.current_version is not None
        versions = [
            VersionSummary(
                version=v.version,
                content_hash=v.content_hash,
                jev_model=v.jev_model,
                created_at=v.created_at,
                is_current=v.id == rule.current_version_id,
                is_live=v.id == rule.live_version_id,
            )
            for v in self.repo.list_versions(rule.id)
        ]
        return RuleDetail(
            **self._summary_fields(rule),
            current=to_rule_version(rule.current_version),
            live=to_rule_version(rule.live_version) if rule.live_version else None,
            versions=versions,
        )
