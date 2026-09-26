"""Load rule packs and check requests from YAML/JSON files."""

import json
from pathlib import Path
from typing import Any

import yaml

from precheck.schema.check_request import CheckRequest
from precheck.schema.rule import RulePack


def load_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def load_rule_pack(path: Path) -> RulePack:
    return RulePack.model_validate(load_data(path))


def load_check_request(path: Path) -> CheckRequest:
    return CheckRequest.model_validate(load_data(path))
