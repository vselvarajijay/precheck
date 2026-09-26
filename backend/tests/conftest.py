import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from precheck.api.app import create_app
from precheck.config import Settings, get_settings

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("template") / "template.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture
def db_path(tmp_path: Path, migrated_template: Path) -> Path:
    """A fresh, fully migrated SQLite file per test."""
    path = tmp_path / "app.db"
    shutil.copy(migrated_template, path)
    return path


_SETTINGS_ENV = ("TYPESAFE_API_KEY", "JEV_BASE_URL", "ANTHROPIC_API_KEY", "DB_PATH", "HOST", "PORT")


@pytest.fixture(autouse=True)
def _isolate_settings_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's/container's real settings or keys (except `live`)."""
    if request.node.get_closest_marker("live"):
        return
    for name in _SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make_client(db_path: Path) -> Iterator[object]:
    """Build a TestClient with an overridden Settings (never reads the real .env)."""
    clients: list[TestClient] = []

    def _make(**overrides: object) -> TestClient:
        app = create_app()
        overrides.setdefault("db_path", db_path)
        settings = Settings(_env_file=None, **overrides)  # type: ignore[arg-type]
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()
