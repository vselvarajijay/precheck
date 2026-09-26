"""`pytest -k translator_lints`"""

from precheck.core.schema import RuleSpec
from precheck.translator.draft import Requirement
from precheck.translator.lints import lint_routing, lint_rule


def spec(
    question: str,
    state: list[str],
    criteria: dict | None = None,
    source: str = "x",
    det: bool = False,
) -> RuleSpec:
    q: dict = {"type": "noul", "instructions": question}
    if criteria:
        q["criteria"] = criteria
    body: dict = {
        "jev": {
            "state_template": state,
            "questions": {"q": q},
            "outcomes": {"q": {"type": "noul", "bands": {"escalate_at": 0.4, "deny_at": 0.7}}},
        }
    }
    if det:
        body["deterministic"] = {
            "predicate": {"op": "gt", "path": "request.args.amount", "value": 1},
            "verdict_when_true": "escalate",
        }
    return RuleSpec.model_validate(
        {"id": "r", "name": "R", "gate": "tool_call", "source_text": source, "body": body}
    )


GOOD = {
    "true": "The destination names another card entirely",
    "false": "The destination is the same card used",
}


def codes(rule: RuleSpec) -> list[str]:
    return [w.code for w in lint_rule(rule, [])]


def test_translator_lints_numeric_question_warns() -> None:
    assert "numeric_question" in codes(
        spec("Is the refund more than 500 dollars?", ["request"], GOOD)
    )
    assert "numeric_question" in codes(
        spec("Is this within 30 days of purchase?", ["request"], GOOD)
    )
    assert "numeric_question" not in codes(
        spec("Does the reason justify the refund?", ["request", "reason"], GOOD)
    )


def test_translator_lints_missing_state_field_warns() -> None:
    c = codes(spec("Does the stated reason justify this refund?", ["request"], GOOD))
    assert "state_missing_field" in c
    assert "state_missing_field" not in codes(
        spec("Does the stated reason justify this refund?", ["request", "reason"], GOOD)
    )
    assert "state_missing_field" in codes(
        spec("Was this card used in an earlier lookup?", ["request"], GOOD)
    )
    assert "state_missing_field" not in codes(
        spec("Was this card used in an earlier lookup?", ["request", "history"], GOOD)
    )


def test_translator_lints_vague_criteria() -> None:
    assert "vague_criteria" in codes(spec("Is it bad?", ["request"]))
    assert "vague_criteria" in codes(
        spec("Is it bad?", ["request"], {"true": "yes", "false": "no"})
    )
    assert "vague_criteria" not in codes(spec("Is it bad?", ["request"], GOOD))


def test_translator_lints_numbers_in_source_without_predicate() -> None:
    assert "numeric_without_predicate" in codes(
        spec("Is it bad?", ["request"], GOOD, source="Refunds over $500")
    )
    assert "numeric_without_predicate" not in codes(
        spec("Is it bad?", ["request"], GOOD, source="Refunds over $500", det=True)
    )


def test_translator_lints_routing_mismatch() -> None:
    reqs = [
        Requirement(
            source_sentence="s",
            requirement="amount over 500",
            routing="deterministic",
            routing_reason="n",
        )
    ]
    warns = lint_routing(reqs, [spec("Is it bad?", ["request"], GOOD)])
    assert [w.code for w in warns] == ["routing_mismatch"]
