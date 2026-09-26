"""Map one Jev answer to a verdict via the rule's outcome definition."""

from precheck.schema import (
    Bands,
    ChoiceAnswer,
    ChoiceOutcome,
    JevAnswer,
    NoulAnswer,
    NoulOutcome,
    Outcome,
    QuestionResult,
    ScoreAnswer,
    ScoreOutcome,
    Verdict,
)


class OutcomeError(ValueError):
    """The answer cannot be mapped (wrong type, unknown option)."""


def _band(bands: Bands, value: float) -> tuple[Verdict, str]:
    v = bands.verdict(value)
    if v is Verdict.deny:
        return v, f"deny (>= {bands.deny_at:g})"
    if v is Verdict.escalate:
        return v, f"escalate ([{bands.escalate_at:g}, {bands.deny_at:g}))"
    return v, f"allow (< {bands.escalate_at:g})"


def map_answer(outcome: Outcome, answer: JevAnswer) -> QuestionResult:
    if outcome.type != answer.type:
        raise OutcomeError(f"expected a {outcome.type} answer, got {answer.type}")
    if isinstance(outcome, NoulOutcome) and isinstance(answer, NoulAnswer):
        value = answer.noul if outcome.direction == "high_is_bad" else 1.0 - answer.noul
        verdict, band = _band(outcome.bands, value)
        if outcome.direction == "low_is_bad":
            band += " on 1-p"
        return QuestionResult(answer=answer, verdict=verdict, value=value, band=band)
    if isinstance(outcome, ChoiceOutcome) and isinstance(answer, ChoiceAnswer):
        if answer.confidence < outcome.min_confidence:
            return QuestionResult(
                answer=answer,
                verdict=Verdict.escalate,
                value=answer.confidence,
                band=f"low confidence ({answer.confidence:g} < {outcome.min_confidence:g})",
            )
        if answer.choice not in outcome.map:
            raise OutcomeError(f"Jev chose unknown option {answer.choice!r}")
        verdict = outcome.map[answer.choice]
        return QuestionResult(
            answer=answer,
            verdict=verdict,
            value=answer.confidence,
            band=f"{answer.choice} -> {verdict}",
        )
    if isinstance(outcome, ScoreOutcome) and isinstance(answer, ScoreAnswer):
        if answer.confidence < outcome.min_confidence:
            return QuestionResult(
                answer=answer,
                verdict=Verdict.escalate,
                value=answer.score,
                band=f"low confidence ({answer.confidence:g} < {outcome.min_confidence:g})",
            )
        verdict, band = _band(outcome.bands, answer.score)
        return QuestionResult(answer=answer, verdict=verdict, value=answer.score, band=band)
    raise OutcomeError(f"unsupported outcome/answer pair {outcome.type}")  # pragma: no cover
