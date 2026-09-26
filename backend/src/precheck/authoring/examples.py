"""Bundled examples: playground scenarios and rule packs (backend/examples)."""

import json
from pathlib import Path

from pydantic import BaseModel

from precheck.authoring.errors import NotFoundError
from precheck.schema import CheckRequest, RulePack, Verdict
from precheck.schema.loader import load_rule_pack


class Example(BaseModel):
    id: str
    title: str
    description: str
    pack: str | None = None
    expected_verdict: Verdict | None = None
    check_request: CheckRequest


class PackInfo(BaseModel):
    name: str
    rule_ids: list[str]


def list_examples(examples_dir: Path) -> list[Example]:
    files = sorted((examples_dir / "playground").glob("*.json"))
    return [Example.model_validate(json.loads(f.read_text(encoding="utf-8"))) for f in files]


def list_packs(examples_dir: Path) -> list[PackInfo]:
    return [
        PackInfo(name=f.stem, rule_ids=[r.id for r in load_rule_pack(f).rules])
        for f in sorted((examples_dir / "rulepacks").glob("*.yaml"))
    ]


def get_pack(examples_dir: Path, name: str) -> RulePack:
    path = examples_dir / "rulepacks" / f"{name}.yaml"
    if not name.replace("-", "").replace("_", "").isalnum() or not path.exists():
        raise NotFoundError(f"rule pack {name!r} not found")
    return load_rule_pack(path)
