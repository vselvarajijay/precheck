import json
from pathlib import Path

import httpx
import pytest
import respx

from precheck.jev import FixtureStore, JevClient, JevFixtureMissing, request_hash

from .conftest import BASE, KEY, NOUL, URL, ok_body


@respx.mock
async def test_record_then_replay(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    respx.post(URL).mock(return_value=httpx.Response(200, json=ok_body()))
    async with JevClient(KEY, base_url=BASE, mode="record", fixtures=store) as rec:
        live = await rec.evaluate({"a": 1}, {"q": NOUL})
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    text = files[0].read_text()
    assert KEY not in text and "Authorization" not in text
    assert json.loads(text)["request"]["state"] == {"a": 1}

    replay = JevClient(None, mode="replay", fixtures=store)
    again = await replay.evaluate({"a": 1}, {"q": NOUL})
    assert again.from_fixture and again.answers == live.answers
    assert again.resolved_model == live.resolved_model


async def test_replay_miss_raises_with_request_hash(tmp_path: Path) -> None:
    client = JevClient(None, mode="replay", fixtures=FixtureStore(tmp_path))
    with pytest.raises(JevFixtureMissing) as exc:
        await client.evaluate({"unknown": True}, {"q": NOUL})
    wire = {
        "model": "jev-latest",
        "state": {"unknown": True},
        "questions": {"q": {"type": "noul", "instructions": "Is it risky?"}},
    }
    assert exc.value.request_hash == request_hash(wire)
    assert exc.value.request_hash in str(exc.value)


async def test_replay_makes_no_network_calls(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    wire = {
        "model": "jev-latest",
        "state": "s",
        "questions": {"q": {"type": "noul", "instructions": "Is it risky?"}},
    }
    store.save(wire, ok_body())
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(URL)
        resp = await JevClient(None, mode="replay", fixtures=store).evaluate("s", {"q": NOUL})
    assert route.call_count == 0 and resp.from_fixture


def test_hash_ignores_key_order() -> None:
    a = {"model": "m", "state": {"x": 1, "y": 2}, "questions": {}}
    b = {"questions": {}, "state": {"y": 2, "x": 1}, "model": "m"}
    assert request_hash(a) == request_hash(b)


def test_non_live_mode_requires_fixture_dir() -> None:
    with pytest.raises(ValueError):
        JevClient(KEY, mode="replay")
