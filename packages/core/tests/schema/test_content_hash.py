import copy

from precheck.core.schema import RuleBody, content_hash

from .conftest import noul_rule


def test_content_hash_stable_across_key_order() -> None:
    a = noul_rule()
    b = dict(reversed(list(copy.deepcopy(a).items())))
    b["jev"] = dict(reversed(list(b["jev"].items())))
    assert content_hash(RuleBody.model_validate(a)) == content_hash(RuleBody.model_validate(b))


def test_content_hash_changes_when_instruction_text_changes() -> None:
    a = RuleBody.model_validate(noul_rule())
    edited = noul_rule(questions={"risky": {"type": "noul", "instructions": "Is this risky? "}})
    assert content_hash(a) != content_hash(RuleBody.model_validate(edited))


def test_content_hash_changes_when_threshold_changes() -> None:
    a = RuleBody.model_validate(noul_rule())
    b = RuleBody.model_validate(
        noul_rule(
            outcomes={"risky": {"type": "noul", "bands": {"escalate_at": 0.41, "deny_at": 0.7}}}
        )
    )
    assert content_hash(a) != content_hash(b)


def test_content_hash_format_and_defaults_equivalence() -> None:
    explicit = {**noul_rule(), "severity": "medium", "on_missing": "escalate", "requires": []}
    a = content_hash(RuleBody.model_validate(noul_rule()))
    assert a.startswith("sha256:") and len(a) == 7 + 64
    assert a == content_hash(RuleBody.model_validate(explicit))
