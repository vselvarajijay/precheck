from pathlib import Path
from typing import Any

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def noul_rule(**jev_overrides: Any) -> dict[str, Any]:
    """A minimal valid RuleBody dict with one noul question."""
    jev: dict[str, Any] = {
        "model": "jev-latest",
        "state_template": ["request"],
        "questions": {"risky": {"type": "noul", "instructions": "Is this risky?"}},
        "outcomes": {"risky": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}}},
    }
    jev.update(jev_overrides)
    return {"jev": jev}


@pytest.fixture
def examples() -> Path:
    return EXAMPLES
