from typing import Any

import pytest
from pydantic import TypeAdapter

from precheck.core.schema import Predicate, describe_predicate, evaluate_predicate, predicate_paths

P: TypeAdapter[Any] = TypeAdapter(Predicate)

DATA = {
    "gate": "tool_call",
    "agent": {"id": "support-bot"},
    "request": {
        "kind": "external_call",
        "tool": "http_request",
        "url": "https://api.Pastebin.com:443/api/post?x=1",
        "args": {
            "amount": 620,
            "amount_str": "620.00",
            "flag": True,
            "email": "a@corp.example.com",
        },
    },
    "history": [{"tool": "lookup_order"}, {"tool": "read_customer_profile"}],
    "reason": "  Customer asked  ",
}


def ev(pred: dict[str, Any]) -> bool:
    return evaluate_predicate(P.validate_python(pred), DATA)


@pytest.mark.parametrize(
    ("pred", "expected"),
    [
        ({"op": "exists", "path": "reason"}, True),
        ({"op": "exists", "path": "context.user_goal"}, False),
        ({"op": "missing", "path": "context.user_goal"}, True),
        ({"op": "missing", "path": "reason"}, False),
        ({"op": "eq", "path": "request.tool", "value": "http_request"}, True),
        ({"op": "eq", "path": "request.tool", "value": "HTTP_REQUEST"}, False),
        ({"op": "ne", "path": "request.tool", "value": "issue_refund"}, True),
        ({"op": "eq", "path": "request.args.flag", "value": True}, True),
        ({"op": "eq", "path": "request.args.flag", "value": 1}, False),
        ({"op": "gt", "path": "request.args.amount", "value": 500}, True),
        ({"op": "gt", "path": "request.args.amount", "value": 620}, False),
        ({"op": "gte", "path": "request.args.amount", "value": 620}, True),
        ({"op": "lt", "path": "request.args.amount", "value": 620.5}, True),
        ({"op": "lte", "path": "request.args.amount", "value": 619}, False),
        ({"op": "gt", "path": "request.args.amount_str", "value": 500}, True),
        ({"op": "gt", "path": "request.args.flag", "value": 0}, False),
        ({"op": "gt", "path": "request.tool", "value": 0}, False),
        ({"op": "gt", "path": "request.args.missing", "value": 0}, False),
        ({"op": "in", "path": "request.tool", "values": ["a", "http_request"]}, True),
        ({"op": "not_in", "path": "request.tool", "values": ["a", "b"]}, True),
        ({"op": "not_in", "path": "request.tool", "values": ["http_request"]}, False),
        ({"op": "regex", "path": "reason", "pattern": "(?i)customer"}, True),
        ({"op": "regex", "path": "reason", "pattern": "^Customer"}, False),
        ({"op": "regex", "path": "request.args.amount", "pattern": "6"}, False),
        ({"op": "min_len", "path": "reason", "value": 14}, True),
        ({"op": "min_len", "path": "reason", "value": 15}, False),
        ({"op": "min_len", "path": "history", "value": 2}, True),
        ({"op": "domain_in", "path": "request.url", "domains": ["pastebin.com"]}, True),
        ({"op": "domain_in", "path": "request.url", "domains": ["bin.com"]}, False),
        ({"op": "domain_not_in", "path": "request.url", "domains": ["example.com"]}, True),
        ({"op": "domain_in", "path": "request.args.email", "domains": ["example.com"]}, True),
        ({"op": "domain_not_in", "path": "request.args.missing", "domains": ["x.com"]}, False),
        ({"op": "eq", "path": "history[*].tool", "value": "read_customer_profile"}, True),
        ({"op": "eq", "path": "history[*].tool", "value": "delete_customer"}, False),
        (
            {"op": "not", "predicate": {"op": "eq", "path": "history[*].tool", "value": "x"}},
            True,
        ),
        ({"op": "exists", "path": "history[*].tool"}, True),
        (
            {
                "op": "all",
                "predicates": [
                    {"op": "eq", "path": "request.tool", "value": "http_request"},
                    {"op": "gt", "path": "request.args.amount", "value": 1},
                ],
            },
            True,
        ),
        (
            {
                "op": "any",
                "predicates": [
                    {"op": "eq", "path": "request.tool", "value": "nope"},
                    {"op": "missing", "path": "agent.purpose"},
                ],
            },
            True,
        ),
    ],
)
def test_evaluate(pred: dict[str, Any], expected: bool) -> None:
    assert ev(pred) is expected


def test_regex_is_linear_time() -> None:
    # Catastrophic for backtracking engines; RE2 answers instantly.
    pred = P.validate_python({"op": "regex", "path": "reason", "pattern": "(a+)+$"})
    assert evaluate_predicate(pred, {"reason": "a" * 50_000 + "b"}) is False


def test_predicate_paths_and_describe() -> None:
    pred = P.validate_python(
        {
            "op": "all",
            "predicates": [
                {"op": "eq", "path": "request.tool", "value": "issue_refund"},
                {
                    "op": "not",
                    "predicate": {"op": "gt", "path": "request.args.amount", "value": 500},
                },
                {"op": "exists", "path": "request.tool"},
            ],
        }
    )
    assert predicate_paths(pred) == ["request.tool", "request.args.amount"]
    assert describe_predicate(pred) == (
        "(request.tool == 'issue_refund' AND NOT request.args.amount > 500 AND request.tool exists)"
    )
