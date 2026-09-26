"""Lab settings: the test agent talks only to the proxy; mock tools need none."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr

from precheck.core.settings import EXAMPLES_DIR, FIXTURES_DIR, BaseAppSettings


class LabSettings(BaseAppSettings):
    anthropic_api_key: SecretStr | None = None
    llm_mode: Literal["live", "record", "replay", "cache"] = "live"
    llm_fixtures_dir: Path = FIXTURES_DIR / "llm"
    examples_dir: Path = EXAMPLES_DIR
    proxy_agents_file: Path = EXAMPLES_DIR / "agents.yaml"
    proxy_default_agent: str = "support-bot"
    api_url: str = "http://127.0.0.1:8000"
    agent_proxy_url: str = "http://127.0.0.1:8200/mcp"
    agent_tools_url: str = "http://127.0.0.1:8100"
    agent_model: str = "claude-sonnet-5"
    agent_max_turns: int = 8

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())


@lru_cache
def get_settings() -> LabSettings:
    return LabSettings()
