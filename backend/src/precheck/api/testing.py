"""Test-only hooks, mounted only when ENABLE_TEST_RESET=true (the isolated e2e stack)."""

from fastapi import APIRouter
from sqlalchemy import delete, update

from precheck.api.deps import SessionFactoryDep, SettingsDep
from precheck.authoring.seed import seed_demo
from precheck.db.engine import session_scope
from precheck.db.models import (
    BusinessCase,
    EscalationRow,
    LabDecisionRow,
    LabRunRow,
    LabRunStepRow,
    PlaygroundRunRow,
    PolicyVersionRow,
    RuleRow,
    RuleVersionRow,
    SettingRow,
    TestCaseRow,
    TestResultRow,
    TestRunRow,
)

router = APIRouter(prefix="/api/testing", tags=["testing"], include_in_schema=False)


@router.post("/seed-demo")
def seed(db: SessionFactoryDep, settings: SettingsDep) -> dict[str, list[str]]:
    """Seed the demo pack as live rules (isolated stacks start empty)."""
    with session_scope(db) as s:
        return {"created": seed_demo(s, settings.examples_dir)}


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
            PolicyVersionRow,
            LabDecisionRow,
            EscalationRow,
            LabRunStepRow,
            LabRunRow,
        ):
            s.execute(delete(model))
