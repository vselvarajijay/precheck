from pathlib import Path

import pytest

from precheck.translator.llm import (
    ClaudeClient,
    LLMError,
    LLMNotConfigured,
    LLMResponse,
    LLMUsage,
    request_hash,
)

KEY = "fake-anthropic-key-789"


async def test_record_then_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = ClaudeClient(KEY, mode="record", fixtures_dir=tmp_path)

    async def fake_call(request: dict) -> LLMResponse:
        return LLMResponse(
            text='{"ok": true}',
            model="claude-sonnet-5",
            stop_reason="end_turn",
            usage=LLMUsage(input_tokens=10, output_tokens=5),
        )

    monkeypatch.setattr(rec, "_call", fake_call)
    args = {
        "system": "sys",
        "messages": [{"role": "user", "content": "hi"}],
        "schema": {"type": "object"},
    }
    live = await rec.complete_json(**args)
    [f] = list(tmp_path.glob("*.json"))
    assert KEY not in f.read_text()
    assert f.stem == request_hash(rec.build_request(**args))
    again = await ClaudeClient(None, mode="replay", fixtures_dir=tmp_path).complete_json(**args)
    assert again.from_fixture and again.text == live.text and again.usage == live.usage


async def test_replay_miss_is_loud(tmp_path: Path) -> None:
    with pytest.raises(LLMError, match="no recorded LLM fixture"):
        await ClaudeClient(None, mode="replay", fixtures_dir=tmp_path).complete_json(
            system="s", messages=[], schema={}
        )


async def test_live_without_key_is_not_configured() -> None:
    with pytest.raises(LLMNotConfigured):
        await ClaudeClient(None).complete_json(system="s", messages=[], schema={})


def test_request_caches_system_prompt_and_sets_effort() -> None:
    req = ClaudeClient(KEY, effort="low").build_request(
        system="sys", messages=[], schema={"type": "object"}
    )
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert KEY not in repr(ClaudeClient(KEY))


def test_cost_estimate() -> None:
    u = LLMUsage(input_tokens=1_000_000, output_tokens=100_000, cache_read_input_tokens=1_000_000)
    assert u.cost_usd("claude-sonnet-5") == pytest.approx(2.0 + 1.0 + 0.2)


async def test_cache_mode_calls_once_then_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = ClaudeClient(KEY, mode="cache", fixtures_dir=tmp_path)
    calls = 0

    async def fake_call(request: dict) -> LLMResponse:
        nonlocal calls
        calls += 1
        return LLMResponse(text="{}", model="m", stop_reason="end_turn", usage=LLMUsage())

    monkeypatch.setattr(client, "_call", fake_call)
    args = {"system": "s", "messages": [{"role": "user", "content": "x"}], "schema": {}}
    first = await client.complete_json(**args)
    second = await client.complete_json(**args)
    assert calls == 1 and not first.from_fixture and second.from_fixture
