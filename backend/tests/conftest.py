from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from precheck.api.app import create_app
from precheck.config import Settings, get_settings

_SETTINGS_ENV = ("TYPESAFE_API_KEY", "JEV_BASE_URL", "ANTHROPIC_API_KEY", "DB_PATH", "HOST", "PORT")


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's/container's real settings or keys."""
    for name in _SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make_client() -> Iterator[object]:
    """Build a TestClient with an overridden Settings (never reads the real .env)."""
    clients: list[TestClient] = []

    def _make(**overrides: object) -> TestClient:
        app = create_app()
        settings = Settings(_env_file=None, **overrides)  # type: ignore[arg-type]
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()
