from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from precheck.db.engine import make_engine
from precheck.db.models import Base

from ..conftest import alembic_config

TABLES = {
    "business_cases",
    "rules",
    "rule_versions",
    "test_cases",
    "test_runs",
    "test_results",
    "playground_runs",
    "settings",
}


def test_migration_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    cfg = alembic_config(db)
    command.upgrade(cfg, "head")
    assert set(inspect(make_engine(db)).get_table_names()) >= TABLES
    command.downgrade(cfg, "base")
    assert set(inspect(make_engine(db)).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    assert set(inspect(make_engine(db)).get_table_names()) >= TABLES


def test_migration_matches_models(db_path: Path) -> None:
    with make_engine(db_path).connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diffs == []


def test_sqlite_pragmas(db_path: Path) -> None:
    with make_engine(db_path).connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
