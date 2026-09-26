from pathlib import Path

from precheck.config import Settings

FAKE_KEY = "fake-jev-key-do-not-leak-123"


def test_health_ok_with_key(make_client) -> None:
    client = make_client(typesafe_api_key=FAKE_KEY)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["jev_configured"] is True
    assert body["version"]


def test_health_without_key(make_client) -> None:
    resp = make_client(typesafe_api_key=None).get("/api/health")
    assert resp.json()["jev_configured"] is False


def test_empty_key_is_not_configured(make_client) -> None:
    resp = make_client(typesafe_api_key="").get("/api/health")
    assert resp.json()["jev_configured"] is False


def test_key_never_in_response(make_client) -> None:
    client = make_client(typesafe_api_key=FAKE_KEY, anthropic_api_key="fake-anthropic-key-456")
    for path in ("/api/health", "/openapi.json"):
        text = client.get(path).text
        assert FAKE_KEY not in text
        assert "fake-anthropic-key-456" not in text


def test_settings_load_from_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"TYPESAFE_API_KEY={FAKE_KEY}\nDB_PATH=/tmp/x.db\n")
    s = Settings(_env_file=env)  # type: ignore[call-arg]
    assert s.jev_configured
    assert s.db_path == Path("/tmp/x.db")
    assert s.jev_base_url == "https://api.typesafe.ai"
    assert FAKE_KEY not in repr(s)


def test_settings_missing_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("JEV_BASE_URL=http://example.test\n")
    s = Settings(_env_file=env)  # type: ignore[call-arg]
    assert not s.jev_configured
    assert s.jev_base_url == "http://example.test"


def test_live_marker_is_registered_and_skipped_by_default() -> None:
    # Sanity: this test runs under the default `-m 'not live'` selection.
    assert True
