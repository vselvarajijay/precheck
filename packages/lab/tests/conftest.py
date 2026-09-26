import pytest

_SETTINGS_ENV = ("TYPESAFE_API_KEY", "JEV_BASE_URL", "ANTHROPIC_API_KEY", "DB_PATH", "HOST", "PORT")


@pytest.fixture(autouse=True)
def _isolate_settings_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's/container's real settings or keys (except `live`)."""
    if request.node.get_closest_marker("live"):
        return
    for name in _SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)
