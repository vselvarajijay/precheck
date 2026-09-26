"""Settings shared by every package: repo paths and the Jev client configuration.

Each app (server, MCP proxy, lab) builds its own settings class on top of these; the core
itself never reads global settings, callers pass them in.
"""

import os
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/core/src/precheck/core/settings.py -> repo root is five parents up.
# PRECHECK_ROOT overrides it when the packages are installed outside the repo.
REPO_ROOT = Path(os.environ.get("PRECHECK_ROOT") or Path(__file__).resolve().parents[5])
EXAMPLES_DIR = REPO_ROOT / "examples"
FIXTURES_DIR = REPO_ROOT / "fixtures"


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class JevSettings(BaseAppSettings):
    typesafe_api_key: SecretStr | None = None
    jev_base_url: str = "https://api.typesafe.ai"
    # live: call Jev; record: call + save fixtures; replay: fixtures only (tests/CI).
    jev_mode: Literal["live", "record", "replay"] = "live"
    jev_fixtures_dir: Path = FIXTURES_DIR / "jev"
    jev_deadline_s: float = 5.0
    jev_default_model: str = "jev-latest"

    @property
    def jev_configured(self) -> bool:
        return bool(self.typesafe_api_key and self.typesafe_api_key.get_secret_value())
