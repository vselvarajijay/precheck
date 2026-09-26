"""Dotted paths into a CheckRequest, e.g. `request.args.amount`, `history[*].tool`.

Grammar: segment ('.' segment)*, where segment = name ('[' (index | '*') ']')?.
The first segment must be a CheckRequest field. Resolution works on the JSON form of the
request (`model_dump(mode="json", exclude_none=True)`), so absent and null fields are both
MISSING. A `[*]` wildcard fans out: the result is a list of the values found (missing ones
skipped), and predicates treat such a list with "any element matches" semantics.
"""

import re
from dataclasses import dataclass
from typing import Annotated, Any, Final

from pydantic import AfterValidator

CHECK_REQUEST_ROOTS: Final = frozenset({"gate", "agent", "context", "history", "request", "reason"})

_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)(?:\[(\*|\d+)\])?$")


class _Missing:
    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()


@dataclass(frozen=True)
class Resolved:
    """Result of resolving a path. `many` is True when a wildcard was used."""

    value: Any
    many: bool

    @property
    def missing(self) -> bool:
        return self.value is MISSING or (self.many and not self.value)

    def values(self) -> list[Any]:
        """The candidate values: one value, the fanned-out list, or none when missing."""
        if self.many:
            return list(self.value)
        return [] if self.value is MISSING else [self.value]


def parse_path(path: str) -> list[tuple[str, str | None]]:
    """Split a path into (name, index) segments; index is None, '*' or a digit string."""
    if not path or path.strip() != path:
        raise ValueError(f"invalid path {path!r}: empty or surrounded by whitespace")
    segments: list[tuple[str, str | None]] = []
    for raw in path.split("."):
        m = _SEGMENT.match(raw)
        if not m:
            raise ValueError(f"invalid path {path!r}: bad segment {raw!r}")
        segments.append((m.group(1), m.group(2)))
    if segments[0][0] not in CHECK_REQUEST_ROOTS:
        roots = ", ".join(sorted(CHECK_REQUEST_ROOTS))
        raise ValueError(f"invalid path {path!r}: must start with one of: {roots}")
    return segments


def _validate_path(path: str) -> str:
    parse_path(path)
    return path


# Use as a field type wherever a model stores a CheckRequest path.
CheckPath = Annotated[str, AfterValidator(_validate_path)]


def _step(value: Any, name: str, index: str | None) -> list[Any] | Any:
    if not isinstance(value, dict) or name not in value or value[name] is None:
        return MISSING
    value = value[name]
    if index is None:
        return value
    if not isinstance(value, list):
        return MISSING
    if index == "*":
        return value
    i = int(index)
    return value[i] if i < len(value) else MISSING


def resolve(data: dict[str, Any], path: str) -> Resolved:
    """Resolve `path` against the JSON form of a CheckRequest."""
    currents: list[Any] = [data]
    many = False
    for name, index in parse_path(path):
        nxt: list[Any] = []
        for cur in currents:
            got = _step(cur, name, index)
            if got is MISSING:
                continue
            if index == "*":
                nxt.extend(v for v in got if v is not None)
            else:
                nxt.append(got)
        if index == "*":
            many = True
        currents = nxt
    if many:
        return Resolved(currents, many=True)
    return Resolved(currents[0] if currents else MISSING, many=False)
