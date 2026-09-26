"""Load lab scenarios (examples/scenarios/*.yaml)."""

from pathlib import Path

import yaml

from precheck.core.schema.scenario import Scenario


def load_scenarios(directory: Path) -> list[Scenario]:
    return [
        Scenario.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
        for f in sorted(directory.glob("*.yaml"))
    ]


def get_scenario(directory: Path, scenario_id: str) -> Scenario | None:
    path = directory / f"{scenario_id}.yaml"
    if not scenario_id.replace("-", "").isalnum() or not path.exists():
        return None
    return Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
