"""Runtime settings, loaded from the environment and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/precheck/config.py -> repo root is three parents above `src`.
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    typesafe_api_key: SecretStr | None = None
    jev_base_url: str = "https://api.typesafe.ai"
    # live: call Jev; record: call + save fixtures; replay: fixtures only (tests/CI).
    jev_mode: Literal["live", "record", "replay"] = "live"
    jev_fixtures_dir: Path = REPO_ROOT / "backend" / "tests" / "fixtures" / "jev"
    jev_deadline_s: float = 5.0
    jev_default_model: str = "jev-latest"
    anthropic_api_key: SecretStr | None = None
    # Translator LLM (Claude). LLM_MODE mirrors JEV_MODE: live | record | replay.
    translator_model: str = "claude-sonnet-5"
    translator_effort: Literal["low", "medium", "high"] = "low"
    llm_mode: Literal["live", "record", "replay", "cache"] = "live"
    llm_fixtures_dir: Path = REPO_ROOT / "backend" / "tests" / "fixtures" / "llm"
    examples_dir: Path = REPO_ROOT / "backend" / "examples"
    # Seed backend/examples/rulepacks/demo.yaml as live rules on API start (idempotent).
    seed_demo: bool = False
    # Enforcement MCP proxy (data plane).
    api_url: str = "http://127.0.0.1:8000"
    proxy_upstream_url: str = "http://127.0.0.1:8100/mcp"
    proxy_refresh_s: float = 5.0
    proxy_agents_file: Path = REPO_ROOT / "backend" / "examples" / "agents.yaml"
    proxy_default_agent: str = "support-bot"
    proxy_inject_reason: bool = True
    proxy_log_check_requests: bool = True  # lab default; set false to log decisions only
    # Where the API reaches the test-agent service (Agent Lab relays runs through the API).
    agent_url: str = "http://127.0.0.1:8300"
    # Test agent (lab): talks only to the proxy.
    agent_proxy_url: str = "http://127.0.0.1:8200/mcp"
    agent_tools_url: str = "http://127.0.0.1:8100"
    agent_model: str = "claude-sonnet-5"
    agent_max_turns: int = 8
    # Only the isolated e2e stack sets this: exposes POST /api/testing/reset.
    enable_test_reset: bool = False
    db_path: Path = REPO_ROOT / "data" / "app.db"
    # 0.0.0.0 inside containers; safety comes from publishing ports on 127.0.0.1 only.
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def jev_configured(self) -> bool:
        return bool(self.typesafe_api_key and self.typesafe_api_key.get_secret_value())

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
