import json
import logging

import httpx
import pytest
import respx

from precheck.jev import (
    JevAuthError,
    JevClient,
    JevError,
    JevTimeout,
    JevUnavailable,
    JevValidationError,
)

from .conftest import BASE, CHOICE, KEY, NOUL, SCORE, URL, SleepRecorder, ok_body


@respx.mock
async def test_parses_every_answer_type(client: JevClient) -> None:
    answers = {
        "n": {"type": "noul", "noul": 0.97},
        "c": {
            "type": "choice",
            "choice": "a",
            "confidence": 1.0,
            "probabilities": {"a": 1, "b": 0},
        },
        "s": {
            "type": "score",
            "score": 2.23,
            "confidence": 0.59,
            "legend": {"0": "low", "1": "mid", "2": "high"},
            "probabilities": {"0": 0.02, "1": 0.73, "2": 0.25},
        },
    }
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200, json=ok_body(answers), headers={"x-typesafe-request-id": "req_1"}
        )
    )
    resp = await client.evaluate({"x": 1}, {"n": NOUL, "c": CHOICE, "s": SCORE}, "jev-latest")
    assert resp.resolved_model == "jev-1.13.0"
    assert resp.answers["n"].noul == 0.97  # type: ignore[union-attr]
    assert resp.answers["c"].choice == "a"  # type: ignore[union-attr]
    assert resp.answers["s"].score == 2.23  # type: ignore[union-attr]
    assert resp.usage.input_tokens == 123
    assert resp.request_id == "req_1"
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "jev-latest" and sent["state"] == {"x": 1}
    assert sent["questions"]["n"] == {"type": "noul", "instructions": "Is it risky?"}
    assert route.calls[0].request.headers["authorization"] == f"Bearer {KEY}"


@respx.mock
async def test_jev_retry_429_then_200(client: JevClient, sleeps: SleepRecorder) -> None:
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(529), httpx.Response(200, json=ok_body())]
    )
    resp = await client.evaluate("s", {"q": NOUL})
    assert resp.answers["q"].noul == 0.9  # type: ignore[union-attr]
    assert route.call_count == 3
    assert len(sleeps.calls) == 2
    assert all(0 <= s <= 0.2 * 2**i for i, s in enumerate(sleeps.calls))


@respx.mock
async def test_jev_retry_on_5xx_and_transport_errors(client: JevClient) -> None:
    respx.post(URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("boom"),
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json=ok_body()),
        ]
    )
    resp = await client.evaluate("s", {"q": NOUL})
    assert resp.resolved_model == "jev-1.13.0"


@respx.mock
async def test_jev_retry_401_not_retried(client: JevClient) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(JevAuthError):
        await client.evaluate("s", {"q": NOUL})
    assert route.call_count == 1


@respx.mock
async def test_jev_retry_422_not_retried_body_surfaced(client: JevClient) -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(422, json={"detail": "criteria must have 2-10 levels"})
    )
    with pytest.raises(JevValidationError) as exc:
        await client.evaluate("s", {"q": NOUL})
    assert route.call_count == 1
    assert exc.value.status == 422
    assert "criteria must have 2-10 levels" in exc.value.body


@respx.mock
async def test_jev_retry_exhausted_is_unavailable(client: JevClient) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(429))
    with pytest.raises(JevUnavailable, match="after 4 attempts"):
        await client.evaluate("s", {"q": NOUL})
    assert route.call_count == 4


@respx.mock
async def test_jev_retry_deadline_exceeded_is_timeout() -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    client = JevClient(KEY, base_url=BASE, deadline_s=0.05, max_retries=1000, backoff_base_s=0.01)
    with pytest.raises(JevTimeout, match=r"deadline of 0\.05s exceeded"):
        await client.evaluate("s", {"q": NOUL})


@respx.mock
async def test_jev_retry_deadline_while_backing_off() -> None:
    respx.post(URL).mock(return_value=httpx.Response(529))
    client = JevClient(KEY, base_url=BASE, deadline_s=0.08, max_retries=1000, backoff_base_s=0.02)
    with pytest.raises(JevTimeout):
        await client.evaluate("s", {"q": NOUL})


async def test_missing_key_raises_auth_error() -> None:
    with pytest.raises(JevAuthError, match="not configured"):
        await JevClient(None, base_url=BASE).evaluate("s", {"q": NOUL})


@respx.mock
async def test_unexpected_shape_raises(client: JevClient) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json={"nope": 1}))
    with pytest.raises(JevError, match="unexpected Jev response shape"):
        await client.evaluate("s", {"q": NOUL})


@respx.mock
async def test_resolve_model_is_cached(client: JevClient) -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json=ok_body({"ok": {"type": "noul", "noul": 0.5}}))
    )
    assert await client.resolve_model() == "jev-1.13.0"
    assert await client.resolve_model() == "jev-1.13.0"
    assert route.call_count == 1


@respx.mock
async def test_redaction_key_never_logged_or_repr(
    client: JevClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    respx.post(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=ok_body())])
    await client.evaluate("s", {"q": NOUL})
    with pytest.raises(JevAuthError) as exc:
        respx.post(URL).mock(return_value=httpx.Response(401))
        await client.evaluate("s", {"q": NOUL})
    assert KEY not in caplog.text
    assert KEY not in repr(client)
    assert KEY not in str(exc.value)
    assert "precheck.jev" in caplog.text or "jev status" in caplog.text
