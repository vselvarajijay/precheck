"""Every limit and invariant fails with a clear message (`pytest -k schema_invalid`)."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from precheck.core.schema import CheckRequest, Predicate, RuleBody, RulePack

from .conftest import noul_rule


def _err(model: Any, data: Any, **kw: Any) -> str:
    with pytest.raises(ValidationError) as exc:
        if isinstance(model, TypeAdapter):
            model.validate_python(data, **kw)
        else:
            model.model_validate(data, **kw)
    return str(exc.value)


def _choice(n: int) -> dict[str, Any]:
    opts = {f"opt_{i}": f"option {i}" for i in range(n)}
    return noul_rule(
        questions={"pick": {"type": "choice", "instructions": "Pick one", "criteria": opts}},
        outcomes={"pick": {"type": "choice", "map": dict.fromkeys(opts, "allow")}},
    )


def _score(levels: int, bands: tuple[float, float] = (0.0, 1.0)) -> dict[str, Any]:
    return noul_rule(
        questions={
            "risk": {
                "type": "score",
                "instructions": "How risky?",
                "criteria": [f"level {i}" for i in range(levels)],
            }
        },
        outcomes={
            "risk": {"type": "score", "bands": {"escalate_at": bands[0], "deny_at": bands[1]}}
        },
    )


def test_schema_invalid_choice_zero_options() -> None:
    assert "at least 1 item" in _err(RuleBody, _choice(0))


def test_schema_invalid_choice_256_options() -> None:
    assert "at most 255 items" in _err(RuleBody, _choice(256))


def test_schema_valid_choice_limits() -> None:
    RuleBody.model_validate(_choice(1))
    RuleBody.model_validate(_choice(255))


def test_schema_invalid_score_one_level() -> None:
    assert "at least 2 items" in _err(RuleBody, _score(1, (0, 0)))


def test_schema_invalid_score_eleven_levels() -> None:
    assert "at most 10 items" in _err(RuleBody, _score(11))


def test_schema_valid_score_limits() -> None:
    RuleBody.model_validate(_score(2))
    RuleBody.model_validate(_score(10, (3, 9)))


def test_schema_invalid_score_bands_out_of_range() -> None:
    assert "within [0, 3]" in _err(RuleBody, _score(4, (2, 4)))


def test_schema_invalid_inverted_bands() -> None:
    body = noul_rule(
        outcomes={"risky": {"type": "noul", "bands": {"escalate_at": 0.8, "deny_at": 0.5}}}
    )
    assert "escalate_at (0.8) must be <= deny_at (0.5)" in _err(RuleBody, body)


def test_schema_invalid_noul_bands_over_one() -> None:
    body = noul_rule(
        outcomes={"risky": {"type": "noul", "bands": {"escalate_at": 0.5, "deny_at": 1.5}}}
    )
    assert "within [0, 1]" in _err(RuleBody, body)


def test_schema_invalid_unknown_op() -> None:
    msg = _err(TypeAdapter(Predicate), {"op": "startswith", "path": "reason", "value": "x"})
    assert "does not match any of the expected tags" in msg


def test_schema_invalid_bad_path_root() -> None:
    msg = _err(TypeAdapter(Predicate), {"op": "exists", "path": "args.amount"})
    assert "must start with one of" in msg


def test_schema_invalid_bad_path_syntax() -> None:
    assert "bad segment" in _err(TypeAdapter(Predicate), {"op": "exists", "path": "request..x"})


def test_schema_invalid_ordering_needs_number() -> None:
    msg = _err(TypeAdapter(Predicate), {"op": "gt", "path": "request.args.amount", "value": "big"})
    assert "needs a numeric value" in msg


def test_schema_invalid_bad_regex() -> None:
    msg = _err(TypeAdapter(Predicate), {"op": "regex", "path": "reason", "pattern": "(unclosed"})
    assert "invalid RE2 pattern" in msg


def test_schema_invalid_backreference_regex_rejected_by_re2() -> None:
    assert "invalid RE2 pattern" in _err(
        TypeAdapter(Predicate), {"op": "regex", "path": "reason", "pattern": r"(a)\1"}
    )


def test_schema_invalid_empty_questions() -> None:
    assert "at least 1 item" in _err(RuleBody, noul_rule(questions={}, outcomes={}))


def test_schema_invalid_outcome_missing() -> None:
    assert "outcomes must cover exactly the questions" in _err(RuleBody, noul_rule(outcomes={}))


def test_schema_invalid_outcome_type_mismatch() -> None:
    body = noul_rule(
        outcomes={"risky": {"type": "score", "bands": {"escalate_at": 0, "deny_at": 1}}}
    )
    assert "outcome for 'risky' is 'score' but question is 'noul'" in _err(RuleBody, body)


def test_schema_invalid_choice_map_incomplete() -> None:
    body = _choice(3)
    del body["jev"]["outcomes"]["pick"]["map"]["opt_2"]
    assert "must map every option exactly" in _err(RuleBody, body)


def test_schema_invalid_question_id_with_double_underscore() -> None:
    body = noul_rule(
        questions={"a__b": {"type": "noul", "instructions": "x"}},
        outcomes={"a__b": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}}},
    )
    assert "String should match pattern" in _err(RuleBody, body)


def test_schema_invalid_no_checks() -> None:
    assert "needs a deterministic check, a jev check, or both" in _err(RuleBody, {})


def test_schema_invalid_bad_model_name() -> None:
    assert "String should match pattern" in _err(RuleBody, noul_rule(model="gpt-4"))


def test_schema_invalid_live_rejects_jev_latest() -> None:
    msg = _err(RuleBody, noul_rule(), context={"status": "live"})
    assert "live rules must pin a Jev version" in msg


def test_schema_invalid_live_rejects_jev_preview() -> None:
    msg = _err(RuleBody, noul_rule(model="jev-preview"), context={"status": "live"})
    assert "live rules must pin a Jev version" in msg


def test_live_accepts_pinned_model() -> None:
    body = RuleBody.model_validate(noul_rule(model="jev-1.13.0"), context={"status": "live"})
    assert body.jev is not None and body.jev.pinned


def test_draft_allows_jev_latest() -> None:
    body = RuleBody.model_validate(noul_rule())
    assert body.jev is not None and not body.jev.pinned


def test_schema_invalid_extra_field() -> None:
    assert "Extra inputs are not permitted" in _err(RuleBody, {**noul_rule(), "surprise": 1})


def test_schema_invalid_check_request_requires_request() -> None:
    assert "request" in _err(CheckRequest, {"gate": "tool_call"})


def test_schema_invalid_check_request_bad_gate() -> None:
    msg = _err(CheckRequest, {"gate": "sideways", "request": {"kind": "content", "text": "x"}})
    assert "gate" in msg


@pytest.mark.parametrize(
    ("kind", "field"), [("tool_call", "tool"), ("external_call", "url"), ("content", "text")]
)
def test_schema_invalid_request_kind_fields(kind: str, field: str) -> None:
    msg = _err(CheckRequest, {"gate": "tool_call", "request": {"kind": kind}})
    assert f"requires request.{field}" in msg


def test_schema_invalid_rule_pack_unknown_schema_version() -> None:
    pack = {
        "schema": 2,
        "rules": [{"id": "r", "name": "R", "gate": "tool_call", "body": noul_rule()}],
    }
    assert "schema" in _err(RulePack, pack)


def test_schema_invalid_rule_pack_duplicate_ids() -> None:
    rule = {"id": "r", "name": "R", "gate": "tool_call", "body": noul_rule()}
    assert "duplicate rule ids" in _err(RulePack, {"schema": 1, "rules": [rule, rule]})


@pytest.mark.parametrize("bad_id", ["Refund", "-refund", "refund-", "refund_limit", ""])
def test_schema_invalid_rule_id(bad_id: str) -> None:
    rule = {"id": bad_id, "name": "R", "gate": "tool_call", "body": noul_rule()}
    assert "id" in _err(RulePack, {"schema": 1, "rules": [rule]})
