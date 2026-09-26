"""model -> JSON -> model equality for fixtures of every type."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter

from precheck.core.schema import (
    CheckRequest,
    Decision,
    JevAnswer,
    Predicate,
    RuleBody,
    RulePack,
    RuleVersion,
    content_hash,
)
from precheck.core.schema.loader import load_check_request, load_rule_pack

from .conftest import EXAMPLES, noul_rule


def _roundtrip_model(obj: BaseModel) -> None:
    again = type(obj).model_validate_json(obj.model_dump_json(by_alias=True))
    assert again == obj


def test_roundtrip_rule_pack() -> None:
    _roundtrip_model(load_rule_pack(EXAMPLES / "refund.yaml"))


@pytest.mark.parametrize(
    "path", sorted((EXAMPLES / "requests").glob("*.json")), ids=lambda p: p.stem
)
def test_roundtrip_check_requests(path: Path) -> None:
    _roundtrip_model(load_check_request(path))


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "noul", "noul": 0.97},
        {"type": "choice", "choice": "refund", "confidence": 1.0, "probabilities": {"refund": 1.0}},
        {
            "type": "score",
            "score": 2.23,
            "confidence": 0.59,
            "legend": {"0": "routine"},
            "probabilities": {"0": 0.02},
        },
    ],
)
def test_roundtrip_jev_answers(answer: dict[str, Any]) -> None:
    ta: TypeAdapter[Any] = TypeAdapter(JevAnswer)
    parsed = ta.validate_python(answer)
    assert ta.validate_json(ta.dump_json(parsed)) == parsed
    assert ta.dump_python(parsed, mode="json") == answer


def test_roundtrip_noul_criteria_aliases() -> None:
    body = RuleBody.model_validate(
        noul_rule(
            questions={
                "q": {
                    "type": "noul",
                    "instructions": "x",
                    "criteria": {"true": "yes", "false": "no"},
                }
            },
            outcomes={"q": {"type": "noul", "bands": {"escalate_at": 0.5, "deny_at": 0.5}}},
        )
    )
    dumped = json.loads(body.model_dump_json(by_alias=True))
    assert dumped["jev"]["questions"]["q"]["criteria"] == {"true": "yes", "false": "no"}
    _roundtrip_model(body)


def test_roundtrip_predicate_tree() -> None:
    ta: TypeAdapter[Any] = TypeAdapter(Predicate)
    tree = {
        "op": "any",
        "predicates": [
            {
                "op": "not",
                "predicate": {"op": "domain_in", "path": "request.url", "domains": ["a.com"]},
            },
            {"op": "all", "predicates": [{"op": "min_len", "path": "reason", "value": 3}]},
        ],
    }
    parsed = ta.validate_python(tree)
    assert ta.dump_python(parsed, mode="json") == tree


def test_roundtrip_rule_version_and_decision() -> None:
    body = RuleBody.model_validate(noul_rule())
    rv = RuleVersion(rule_id="r-1", version=1, body=body, content_hash=content_hash(body))
    _roundtrip_model(rv)
    d = Decision.model_validate(
        {
            "verdict": "deny",
            "versions": {"engine": "0.1.0", "schema": 1, "rules": {"r-1": 1}},
            "rule_results": [
                {
                    "rule_id": "r-1",
                    "matched": True,
                    "verdict": "deny",
                    "source": "jev",
                    "jev": {
                        "risky": {
                            "answer": {"type": "noul", "noul": 0.9},
                            "verdict": "deny",
                            "value": 0.9,
                            "band": "deny (>= 0.7)",
                        }
                    },
                }
            ],
        }
    )
    _roundtrip_model(d)


def test_check_request_as_data_drops_nulls() -> None:
    cr = CheckRequest.model_validate(
        {"gate": "egress", "request": {"kind": "content", "text": "hi"}, "reason": None}
    )
    assert cr.as_data() == {"gate": "egress", "request": {"kind": "content", "text": "hi"}}


def test_rule_pack_alias_schema_key() -> None:
    pack = load_rule_pack(EXAMPLES / "refund.yaml")
    assert RulePack.model_validate(pack.model_dump(by_alias=True)) == pack
