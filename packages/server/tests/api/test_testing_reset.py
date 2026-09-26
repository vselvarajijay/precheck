from precheck.server.settings import get_settings


def test_reset_not_mounted_by_default(make_client) -> None:
    assert make_client().post("/api/testing/reset").status_code == 404


def test_reset_clears_everything(make_client, monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_TEST_RESET", "true")
    get_settings.cache_clear()
    try:
        c = make_client(enable_test_reset=True)
        created = c.post("/api/examples/packs/demo/load").json()["created"]
        assert len(c.get("/api/rules").json()) == len(created) > 0
        assert c.post("/api/testing/reset").status_code == 204
        assert c.get("/api/rules?status=all").json() == []
    finally:
        get_settings.cache_clear()
