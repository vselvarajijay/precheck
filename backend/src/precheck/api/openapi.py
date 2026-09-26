"""Dump the OpenAPI schema: `python -m precheck.api.openapi > openapi.json`."""

import json
import sys

from precheck.api.app import create_app


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
