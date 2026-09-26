"""Record/replay of Jev responses keyed by sha256 of the canonical request body.

Fixtures hold only the request (for review) and the response JSON; never headers or keys.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from precheck.core.jev.errors import JevFixtureMissing
from precheck.core.schema import canonical_json


def request_hash(wire: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(wire).encode("utf-8")).hexdigest()


class FixtureStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, wire: dict[str, Any]) -> Path:
        return self.directory / f"{request_hash(wire)}.json"

    def load(self, wire: dict[str, Any]) -> dict[str, Any]:
        path = self.path_for(wire)
        if not path.exists():
            raise JevFixtureMissing(request_hash(wire), str(path))
        if log := os.environ.get("JEV_FIXTURE_LOG"):  # opt-in: find unused fixtures
            with open(log, "a", encoding="utf-8") as f:
                f.write(path.name + "\n")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data["response"]  # type: ignore[no-any-return]

    def save(self, wire: dict[str, Any], response: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(wire)
        record = {"request": wire, "response": response}
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
