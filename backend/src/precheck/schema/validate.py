"""Validate rule packs / check requests: `python -m precheck.schema.validate FILE...`.

A file with a top-level `rules` key is a rule pack; anything else is a check request.
Pass `--live` to also apply the live-publish checks (pinned Jev versions).
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from precheck.schema.check_request import CheckRequest
from precheck.schema.loader import load_data
from precheck.schema.rule import RulePack, live_problems


def validate_file(path: Path, *, live: bool = False) -> tuple[bool, str]:
    try:
        data = load_data(path)
        if isinstance(data, dict) and "rules" in data:
            pack = RulePack.model_validate(data)
            problems = [
                f"{r.id}: {p}" for r in pack.rules for p in (live_problems(r.body) if live else [])
            ]
            if problems:
                return False, "not publishable:\n  " + "\n  ".join(problems)
            return True, f"OK, {len(pack.rules)} rule{'s' if len(pack.rules) != 1 else ''}"
        CheckRequest.model_validate(data)
        return True, "OK, check request"
    except ValidationError as e:
        return False, f"invalid ({e.error_count()} errors):\n{e}"
    except (OSError, ValueError) as e:
        return False, f"error: {e}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--live", action="store_true", help="apply live-publish checks")
    args = parser.parse_args(argv)
    ok_all = True
    for f in args.files:
        ok, msg = validate_file(f, live=args.live)
        ok_all &= ok
        print(f"{f}: {msg}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
