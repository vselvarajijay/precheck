"""Golden-set test cases (minimal CRUD; runs and calibration arrive in slice 09)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from precheck.authoring.errors import NotFoundError
from precheck.db.models import RuleRow, TestCaseRow
from precheck.schema import CheckRequest, Verdict

Origin = Literal["user", "generated", "playground"]


class TestCaseCreate(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = Field(default=None, description="None = policy-wide case")
    name: str = Field(min_length=1, max_length=200)
    check_request: CheckRequest
    expected_verdict: Verdict
    origin: Origin = "user"


class TestCase(BaseModel):
    __test__ = False

    id: str
    rule_id: str | None
    name: str
    check_request: CheckRequest
    expected_verdict: Verdict
    origin: Origin
    created_at: datetime


def _out(row: TestCaseRow) -> TestCase:
    return TestCase(
        id=row.id,
        rule_id=row.rule_id,
        name=row.name,
        check_request=CheckRequest.model_validate(row.check_request_json),
        expected_verdict=Verdict(row.expected_verdict),
        origin=row.origin,
        created_at=row.created_at,
    )


class TestCaseService:
    __test__ = False

    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, data: TestCaseCreate) -> TestCase:
        if data.rule_id is not None and self.s.get(RuleRow, data.rule_id) is None:
            raise NotFoundError(f"rule {data.rule_id!r} not found")
        row = TestCaseRow(
            id=str(uuid.uuid4()),
            rule_id=data.rule_id,
            name=data.name,
            check_request_json=data.check_request.model_dump(mode="json", exclude_none=True),
            expected_verdict=data.expected_verdict.value,
            origin=data.origin,
        )
        self.s.add(row)
        self.s.flush()
        return _out(row)

    def list_for_rule(self, rule_id: str | None) -> list[TestCase]:
        stmt = select(TestCaseRow).order_by(TestCaseRow.created_at)
        stmt = stmt.where(
            TestCaseRow.rule_id == rule_id if rule_id is not None else TestCaseRow.rule_id.is_(None)
        )
        return [_out(r) for r in self.s.scalars(stmt)]
