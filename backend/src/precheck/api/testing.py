"""Test-only hooks, mounted only when ENABLE_TEST_RESET=true (the isolated e2e stack)."""

from fastapi import APIRouter
from sqlalchemy import delete, update

from precheck.api.deps import SessionFactoryDep
from precheck.db.engine import session_scope
from precheck.db.models import (
    BusinessCase,
    PlaygroundRunRow,
    RuleRow,
    RuleVersionRow,
    SettingRow,
    TestCaseRow,
    TestResultRow,
    TestRunRow,
)

router = APIRouter(prefix="/api/testing", tags=["testing"], include_in_schema=False)


@router.post("/reset", status_code=204)
def reset(db: SessionFactoryDep) -> None:
    """Delete every row (FK-safe order) so each e2e test starts from an empty database."""
    with session_scope(db) as s:
        s.execute(update(RuleRow).values(current_version_id=None, live_version_id=None))
        for model in (
            TestResultRow,
            TestRunRow,
            TestCaseRow,
            PlaygroundRunRow,
            RuleVersionRow,
            RuleRow,
            BusinessCase,
            SettingRow,
        ):
            s.execute(delete(model))
