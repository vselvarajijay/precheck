"""Claude client for the translator: structured JSON output, prompt caching, record/replay.

Fixtures are keyed by sha256 of the canonical request (model, system, messages, schema,
effort, max_tokens) and hold only the request and the response text/usage — never keys.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, SecretStr

from precheck.core.schema import canonical_json

if TYPE_CHECKING:
    from precheck.translator.settings import LLMSettings

# cache = replay when a fixture exists, otherwise call live and record (dev/eval runs).
LLMMode = Literal["live", "record", "replay", "cache"]

# USD per 1M tokens (Anthropic first-party list prices, cached 2026-06-24 in the claude-api
# skill). Cache writes cost 1.25x input, cache reads 0.1x input.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class LLMError(Exception):
    """Any failure talking to the LLM (auth, rate limit, refusal, truncation, replay miss)."""


class LLMNotConfigured(LLMError):
    pass


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def cost_usd(self, model: str) -> float:
        inp, out = PRICES.get(model, PRICES["claude-sonnet-5"])
        return (
            self.input_tokens * inp
            + self.cache_creation_input_tokens * inp * 1.25
            + self.cache_read_input_tokens * inp * 0.1
            + self.output_tokens * out
        ) / 1_000_000

    def __add__(self, other: "LLMUsage") -> "LLMUsage":
        return LLMUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
        )


class LLMResponse(BaseModel):
    text: str
    model: str
    stop_reason: str | None
    usage: LLMUsage
    latency_ms: float = 0.0
    request_id: str | None = None
    from_fixture: bool = False


class JsonLLM(Protocol):
    model: str

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        max_tokens: int = ...,
    ) -> LLMResponse: ...


def request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()


class ClaudeClient:
    def __init__(
        self,
        api_key: SecretStr | str | None,
        *,
        model: str = "claude-sonnet-5",
        effort: str = "low",
        mode: LLMMode = "live",
        fixtures_dir: Path | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self.effort = effort
        self.mode: LLMMode = mode
        self.fixtures_dir = fixtures_dir
        if mode != "live" and fixtures_dir is None:
            raise ValueError(f"LLM_MODE={mode} needs a fixtures directory")
        key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._client = anthropic.AsyncAnthropic(api_key=key, timeout=timeout_s) if key else None

    def __repr__(self) -> str:
        return f"ClaudeClient(model={self.model!r}, mode={self.mode!r}, key=***)"

    def build_request(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            # The system prompt is static per prompt version: cache it.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }

    async def complete_json(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        max_tokens: int = 16000,
    ) -> LLMResponse:
        request = self.build_request(
            system=system, messages=messages, schema=schema, max_tokens=max_tokens
        )
        path = (self.fixtures_dir / f"{request_hash(request)}.json") if self.fixtures_dir else None
        if self.mode == "replay" or (self.mode == "cache" and path is not None and path.exists()):
            assert path is not None
            if not path.exists():
                raise LLMError(
                    f"no recorded LLM fixture {path.name}; re-record with LLM_MODE=record"
                )
            data = json.loads(path.read_text(encoding="utf-8"))["response"]
            return LLMResponse.model_validate({**data, "from_fixture": True})
        response = await self._call(request)
        if self.mode in ("record", "cache"):
            assert path is not None
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {"request": request, "response": response.model_dump(exclude={"from_fixture"})}
            path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return response

    async def _call(self, request: dict[str, Any]) -> LLMResponse:
        if self._client is None:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not configured")
        started = time.monotonic()
        try:
            msg = await self._client.messages.create(**request)
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic rate limit; try again shortly") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API") from e
        if msg.stop_reason == "refusal":
            raise LLMError("The model declined this request")
        if msg.stop_reason == "max_tokens":
            raise LLMError(
                "The model's answer was cut off (max_tokens); try a shorter business case"
            )
        text = "".join(b.text for b in msg.content if b.type == "text")
        u = msg.usage
        return LLMResponse(
            text=text,
            model=msg.model,
            stop_reason=msg.stop_reason,
            usage=LLMUsage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_creation_input_tokens=u.cache_creation_input_tokens or 0,
                cache_read_input_tokens=u.cache_read_input_tokens or 0,
            ),
            latency_ms=(time.monotonic() - started) * 1000,
            request_id=getattr(msg, "_request_id", None),
        )


def make_claude_client(settings: "LLMSettings", **overrides: Any) -> ClaudeClient:
    kwargs: dict[str, Any] = {
        "model": settings.translator_model,
        "effort": settings.translator_effort,
        "mode": settings.llm_mode,
        "fixtures_dir": settings.llm_fixtures_dir,
    }
    kwargs.update(overrides)
    return ClaudeClient(settings.anthropic_api_key, **kwargs)
