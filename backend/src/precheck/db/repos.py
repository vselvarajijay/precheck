"""Repository layer: the only code that queries the database. Returns ORM rows; the service
layer converts to schema models."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from precheck.db.models import RuleRow, RuleVersionRow


class RuleRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def get(self, rule_id: str) -> RuleRow | None:
        return self.s.get(RuleRow, rule_id)

    def exists(self, rule_id: str) -> bool:
        return self.s.get(RuleRow, rule_id) is not None

    def search(
        self,
        *,
        gate: str | None = None,
        statuses: Sequence[str] | None = None,
        q: str | None = None,
    ) -> list[RuleRow]:
        stmt = select(RuleRow).order_by(RuleRow.created_at, RuleRow.id)
        if gate:
            stmt = stmt.where(RuleRow.gate == gate)
        if statuses:
            stmt = stmt.where(RuleRow.status.in_(statuses))
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.outerjoin(RuleVersionRow, RuleVersionRow.id == RuleRow.current_version_id)
            stmt = stmt.where(
                or_(
                    func.lower(RuleRow.name).like(like),
                    func.lower(RuleRow.id).like(like),
                    func.lower(RuleVersionRow.source_text).like(like),
                )
            )
        return list(self.s.scalars(stmt))

    def add(self, row: RuleRow) -> RuleRow:
        self.s.add(row)
        self.s.flush()
        return row

    def next_version(self, rule_id: str) -> int:
        current = self.s.scalar(
            select(func.max(RuleVersionRow.version)).where(RuleVersionRow.rule_id == rule_id)
        )
        return (current or 0) + 1

    def add_version(self, row: RuleVersionRow) -> RuleVersionRow:
        self.s.add(row)
        self.s.flush()
        return row

    def get_version(self, rule_id: str, version: int) -> RuleVersionRow | None:
        return self.s.scalar(
            select(RuleVersionRow).where(
                RuleVersionRow.rule_id == rule_id, RuleVersionRow.version == version
            )
        )

    def get_version_by_id(self, version_id: int) -> RuleVersionRow | None:
        return self.s.get(RuleVersionRow, version_id)

    def list_versions(self, rule_id: str) -> list[RuleVersionRow]:
        return list(
            self.s.scalars(
                select(RuleVersionRow)
                .where(RuleVersionRow.rule_id == rule_id)
                .order_by(RuleVersionRow.version)
            )
        )
