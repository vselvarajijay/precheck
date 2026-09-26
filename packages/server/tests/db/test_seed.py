from pathlib import Path

from precheck.core.settings import EXAMPLES_DIR
from precheck.server.authoring.seed import seed_demo
from precheck.server.db.engine import make_engine, session_factory, session_scope
from precheck.server.db.models import PolicyVersionRow, RuleRow


def test_seed_idempotent(db_path: Path) -> None:
    db = session_factory(make_engine(db_path))
    with session_scope(db) as s:
        first = seed_demo(s, EXAMPLES_DIR)
    with session_scope(db) as s:
        second = seed_demo(s, EXAMPLES_DIR)
        rules = s.query(RuleRow).all()
        snapshots = s.query(PolicyVersionRow).count()
    assert len(first) == 7 and second == []
    assert len(rules) == 7 and {r.status for r in rules} == {"live"}
    assert snapshots == 1
