"""Translator LLM (Claude) settings. LLM_MODE mirrors JEV_MODE: live | record | replay | cache."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from precheck.core.settings import FIXTURES_DIR, BaseAppSettings, JevSettings


class LLMSettings(BaseAppSettings):
    anthropic_api_key: SecretStr | None = None
    translator_model: str = "claude-sonnet-5"
    translator_effort: Literal["low", "medium", "high"] = "low"
    llm_mode: Literal["live", "record", "replay", "cache"] = "live"
    llm_fixtures_dir: Path = FIXTURES_DIR / "llm"

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())


class TranslatorToolSettings(LLMSettings, JevSettings):
    """For the eval / round-trip CLIs: Claude to translate, Jev to run generated tests."""


@lru_cache
def get_tool_settings() -> TranslatorToolSettings:
    return TranslatorToolSettings()
