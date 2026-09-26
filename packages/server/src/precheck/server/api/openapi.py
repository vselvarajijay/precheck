"""Dump the OpenAPI schema: `python -m precheck.server.api.openapi > openapi.json`."""

import json
import sys

from precheck.server.api.app import create_app


def main() -> None:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
