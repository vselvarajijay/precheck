"""Control-plane settings, loaded from the environment and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path

from precheck.core.settings import EXAMPLES_DIR, REPO_ROOT, JevSettings
from precheck.translator.settings import LLMSettings


class Settings(LLMSettings, JevSettings):
    examples_dir: Path = EXAMPLES_DIR
    # Seed examples/rulepacks/demo.yaml as live rules on API start (idempotent).
    seed_demo: bool = False
    # Where the API reaches the test-agent service (Agent Lab relays runs through the API).
    agent_url: str = "http://127.0.0.1:8300"
    # Only the isolated e2e stack sets this: exposes POST /api/testing/reset.
    enable_test_reset: bool = False
    db_path: Path = REPO_ROOT / "data" / "app.db"
    # 0.0.0.0 inside containers; safety comes from publishing ports on 127.0.0.1 only.
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
