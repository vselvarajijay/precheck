"""Structured predicate DSL for deterministic checks.

Predicates are data, never code: LLM-authored rules must not reach eval. Every leaf names
a CheckRequest path; semantics are total (no exceptions at evaluation time):

- A missing path makes every leaf false except `missing` (true) and `exists` (false).
- A wildcard path (`history[*].tool`) is true if ANY resolved element satisfies the leaf.
  Use `not` for "none of them".
- Ordering ops (gt/gte/lt/lte) compare numbers; numeric strings ("620.00") are accepted,
  booleans and anything else are false.
- `eq`/`ne`/`in`/`not_in` compare JSON values exactly (strings are case-sensitive).
- `regex` uses RE2 (linear time, no catastrophic backtracking) with `search` semantics.
- `domain_in`/`domain_not_in` extract the host from a URL, email address or bare host and
  match a listed domain exactly or as a subdomain (`api.example.com` is in `example.com`).
"""

import math
from functools import lru_cache
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

import re2
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from precheck.schema.paths import CheckPath, resolve

Scalar = str | int | float | bool | None

MAX_REGEX_LEN = 512


class _Pred(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExistsPredicate(_Pred):
    op: Literal["exists", "missing"]
    path: CheckPath


class ComparePredicate(_Pred):
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    path: CheckPath
    value: Scalar

    @model_validator(mode="after")
    def _numeric_for_ordering(self) -> Self:
        if self.op in ("gt", "gte", "lt", "lte") and _as_number(self.value) is None:
            raise ValueError(f"op {self.op!r} needs a numeric value, got {self.value!r}")
        return self


class SetPredicate(_Pred):
    op: Literal["in", "not_in"]
    path: CheckPath
    values: list[Scalar] = Field(min_length=1)


class RegexPredicate(_Pred):
    op: Literal["regex"]
    path: CheckPath
    pattern: str = Field(min_length=1, max_length=MAX_REGEX_LEN)

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, v: str) -> str:
        try:
            _compile(v)
        except re2.error as e:
            raise ValueError(f"invalid RE2 pattern: {e}") from e
        return v


class MinLenPredicate(_Pred):
    op: Literal["min_len"]
    path: CheckPath
    value: int = Field(ge=0)


class DomainPredicate(_Pred):
    op: Literal["domain_in", "domain_not_in"]
    path: CheckPath
    domains: list[str] = Field(min_length=1)

    @field_validator("domains")
    @classmethod
    def _normalize(cls, v: list[str]) -> list[str]:
        out = []
        for d in v:
            n = d.strip().lower().rstrip(".").removeprefix("*.")
            if not n or "/" in n or " " in n:
                raise ValueError(f"invalid domain {d!r}")
            out.append(n)
        return out


class AllPredicate(_Pred):
    op: Literal["all"]
    predicates: "list[Predicate]" = Field(min_length=1)


class AnyPredicate(_Pred):
    op: Literal["any"]
    predicates: "list[Predicate]" = Field(min_length=1)


class NotPredicate(_Pred):
    op: Literal["not"]
    predicate: "Predicate"


Predicate = Annotated[
    ExistsPredicate
    | ComparePredicate
    | SetPredicate
    | RegexPredicate
    | MinLenPredicate
    | DomainPredicate
    | AllPredicate
    | AnyPredicate
    | NotPredicate,
    Field(discriminator="op"),
]

for _m in (AllPredicate, AnyPredicate, NotPredicate):
    _m.model_rebuild()


# --- evaluation ---------------------------------------------------------------------------


@lru_cache(maxsize=1024)
def _compile(pattern: str) -> Any:
    return re2.compile(pattern)


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        try:
            f = float(v.strip())
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _host_of(v: Any) -> str | None:
    if not isinstance(v, str) or not v.strip():
        return None
    s = v.strip()
    if "://" in s:
        host = urlsplit(s).hostname
    elif "@" in s and "/" not in s:
        host = s.rsplit("@", 1)[1]
    else:
        host = urlsplit("//" + s).hostname
    return host.lower().rstrip(".") if host else None


def _domain_match(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _json_eq(a: Any, b: Any) -> bool:
    # JSON semantics: true is not 1 (Python says it is).
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return bool(a == b)


def _compare(op: str, left: Any, right: Scalar) -> bool:
    if op == "eq":
        return _json_eq(left, right)
    if op == "ne":
        return not _json_eq(left, right)
    a, b = _as_number(left), _as_number(right)
    if a is None or b is None:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]


def _leaf(pred: Any, value: Any) -> bool:
    match pred.op:
        case "eq" | "ne" | "gt" | "gte" | "lt" | "lte":
            return _compare(pred.op, value, pred.value)
        case "in":
            return any(_json_eq(value, v) for v in pred.values)
        case "not_in":
            return not any(_json_eq(value, v) for v in pred.values)
        case "regex":
            return isinstance(value, str) and _compile(pred.pattern).search(value) is not None
        case "min_len":
            return (
                isinstance(value, str | list | dict)
                and len(value.strip() if isinstance(value, str) else value) >= pred.value
            )
        case "domain_in" | "domain_not_in":
            host = _host_of(value)
            if host is None:
                return False
            return _domain_match(host, pred.domains) is (pred.op == "domain_in")
    raise AssertionError(f"unhandled op {pred.op}")  # pragma: no cover


def evaluate_predicate(pred: Predicate, data: dict[str, Any]) -> bool:
    """Evaluate against the JSON form of a CheckRequest (`CheckRequest.as_data()`)."""
    match pred:
        case AllPredicate():
            return all(evaluate_predicate(p, data) for p in pred.predicates)
        case AnyPredicate():
            return any(evaluate_predicate(p, data) for p in pred.predicates)
        case NotPredicate():
            return not evaluate_predicate(pred.predicate, data)
        case ExistsPredicate():
            r = resolve(data, pred.path)
            return (not r.missing) if pred.op == "exists" else r.missing
    return any(_leaf(pred, v) for v in resolve(data, pred.path).values())


def predicate_paths(pred: Predicate) -> list[str]:
    """Every path a predicate reads, in order, de-duplicated."""
    out: list[str] = []

    def walk(p: Any) -> None:
        if isinstance(p, AllPredicate | AnyPredicate):
            for c in p.predicates:
                walk(c)
        elif isinstance(p, NotPredicate):
            walk(p.predicate)
        elif p.path not in out:
            out.append(p.path)

    walk(pred)
    return out


_SYMBOL = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def describe_predicate(pred: Predicate) -> str:
    """Compact human-readable form, e.g. `request.args.amount > 500`."""
    match pred:
        case AllPredicate():
            return "(" + " AND ".join(describe_predicate(p) for p in pred.predicates) + ")"
        case AnyPredicate():
            return "(" + " OR ".join(describe_predicate(p) for p in pred.predicates) + ")"
        case NotPredicate():
            return f"NOT {describe_predicate(pred.predicate)}"
        case ExistsPredicate():
            return f"{pred.path} {'exists' if pred.op == 'exists' else 'is missing'}"
        case ComparePredicate():
            return f"{pred.path} {_SYMBOL[pred.op]} {pred.value!r}"
        case SetPredicate():
            return f"{pred.path} {'in' if pred.op == 'in' else 'not in'} {pred.values!r}"
        case RegexPredicate():
            return f"{pred.path} matches /{pred.pattern}/"
        case MinLenPredicate():
            return f"len({pred.path}) >= {pred.value}"
        case DomainPredicate():
            word = "in" if pred.op == "domain_in" else "not in"
            return f"domain({pred.path}) {word} {pred.domains!r}"
    raise AssertionError("unhandled predicate")  # pragma: no cover
