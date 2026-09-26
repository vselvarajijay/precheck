"""Enforcement MCP proxy settings (data plane)."""

from functools import lru_cache
from pathlib import Path

from precheck.core.settings import EXAMPLES_DIR, JevSettings


class ProxySettings(JevSettings):
    api_url: str = "http://127.0.0.1:8000"
    proxy_upstream_url: str = "http://127.0.0.1:8100/mcp"
    proxy_refresh_s: float = 5.0
    proxy_agents_file: Path = EXAMPLES_DIR / "agents.yaml"
    proxy_default_agent: str = "support-bot"
    proxy_inject_reason: bool = True
    proxy_log_check_requests: bool = True  # lab default; set false to log decisions only
    host: str = "0.0.0.0"


@lru_cache
def get_settings() -> ProxySettings:
    return ProxySettings()
