"""Catches accidental contract changes. Regenerate with UPDATE_SNAPSHOTS=1."""

import json
import os
from pathlib import Path

from precheck.schema.export import export_schemas

SNAPSHOT = Path(__file__).resolve().parents[1] / "snapshots" / "schema.json"


def test_schema_snapshot() -> None:
    current = json.dumps(export_schemas(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.write_text(current)
    assert SNAPSHOT.exists(), "missing snapshot; run with UPDATE_SNAPSHOTS=1"
    assert SNAPSHOT.read_text() == current, (
        "JSON Schema contract changed. If intended, rerun with UPDATE_SNAPSHOTS=1 and commit."
    )
