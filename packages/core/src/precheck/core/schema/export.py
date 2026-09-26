"""Dump the JSON Schemas of the public contracts: `python -m precheck.core.schema.export`."""

import json
import sys
from typing import Any

from pydantic import BaseModel

from precheck.core.schema.check_request import CheckRequest
from precheck.core.schema.rule import Decision, RuleBody, RulePack, RuleVersion

CONTRACTS: dict[str, type[BaseModel]] = {
    "CheckRequest": CheckRequest,
    "RuleBody": RuleBody,
    "RulePack": RulePack,
    "RuleVersion": RuleVersion,
    "Decision": Decision,
}


def export_schemas() -> dict[str, Any]:
    return {name: model.model_json_schema(by_alias=True) for name, model in CONTRACTS.items()}


def main() -> None:
    json.dump(export_schemas(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
