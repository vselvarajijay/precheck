import pytest

from precheck.schema import MISSING, resolve
from precheck.schema.paths import parse_path

DATA = {
    "gate": "tool_call",
    "request": {
        "kind": "tool_call",
        "tool": "issue_refund",
        "args": {"amount": 620, "meta": {"a": 1}},
    },
    "history": [
        {"tool": "lookup_order", "args": {"order_id": "1"}},
        {"tool": "read_customer_profile", "args": {}},
    ],
    "reason": "because",
}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("gate", "tool_call"),
        ("request.tool", "issue_refund"),
        ("request.args.amount", 620),
        ("request.args.meta.a", 1),
        ("history[0].tool", "lookup_order"),
        ("history[1].tool", "read_customer_profile"),
        ("reason", "because"),
    ],
)
def test_resolve_nested(path: str, expected: object) -> None:
    r = resolve(DATA, path)
    assert r.value == expected
    assert not r.many


def test_resolve_wildcard() -> None:
    r = resolve(DATA, "history[*].tool")
    assert r.many
    assert r.values() == ["lookup_order", "read_customer_profile"]


def test_wildcard_skips_missing_elements() -> None:
    r = resolve(DATA, "history[*].args.order_id")
    assert r.values() == ["1"]


@pytest.mark.parametrize(
    "path", ["context.user_goal", "request.args.nope", "history[5].tool", "agent", "reason.x"]
)
def test_resolve_missing_sentinel(path: str) -> None:
    r = resolve(DATA, path)
    assert r.value is MISSING
    assert r.missing
    assert r.values() == []


def test_wildcard_on_missing_list_is_missing() -> None:
    r = resolve({"gate": "ingress"}, "history[*].tool")
    assert r.missing and r.values() == []


def test_missing_is_falsy_singleton() -> None:
    assert not MISSING
    assert repr(MISSING) == "MISSING"


@pytest.mark.parametrize(
    "bad",
    ["", "nope.field", "request..tool", "request.tool[", "request.tool[x]", " request", "a b"],
)
def test_parse_path_rejects_bad_paths(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_path(bad)
