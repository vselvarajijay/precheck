"""Threshold calibration: grid-search a question's bands on stored test answers.

Pure and deterministic: needs only (value, expected verdict) pairs from a previous run,
never new Jev calls. Cost of a prediction: 0 if right; a false allow (expected deny or
escalate, predicted allow) costs the severity weight; any other mistake costs 1. Ties
prefer the safer bands (lower escalate_at, then lower deny_at).
"""

from pydantic import BaseModel

from precheck.core.schema import Bands, Severity, Verdict

FALSE_ALLOW_WEIGHT: dict[Severity, float] = {
    Severity.high: 5.0,
    Severity.medium: 3.0,
    Severity.low: 1.0,
}


class Point(BaseModel):
    value: float
    expected: Verdict


class Suggestion(BaseModel):
    bands: Bands
    cost: float
    correct: int
    total: int

    @property
    def pass_rate(self) -> float:
        return self.correct / self.total if self.total else 0.0


def cost(expected: Verdict, predicted: Verdict, severity: Severity) -> float:
    if expected is predicted:
        return 0.0
    if predicted is Verdict.allow:
        return FALSE_ALLOW_WEIGHT[severity]
    return 1.0


def score(points: list[Point], bands: Bands, severity: Severity) -> Suggestion:
    total_cost = 0.0
    correct = 0
    for p in points:
        predicted = bands.verdict(p.value)
        total_cost += cost(p.expected, predicted, severity)
        correct += predicted is p.expected
    return Suggestion(bands=bands, cost=total_cost, correct=correct, total=len(points))


def calibrate(
    points: list[Point],
    severity: Severity,
    *,
    low: float = 0.0,
    high: float = 1.0,
    step: float = 0.01,
) -> Suggestion:
    """Best (escalate_at, deny_at) on the grid [low, high] with escalate_at <= deny_at."""
    n = round((high - low) / step)
    grid = [round(low + i * step, 6) for i in range(n + 1)]
    weight = FALSE_ALLOW_WEIGHT[severity]
    rank = {Verdict.allow: 0, Verdict.escalate: 1, Verdict.deny: 2}
    pts = [(p.value, rank[p.expected]) for p in points]

    def evaluate_bands(e: float, d: float) -> tuple[float, float]:
        """(cost, margin): margin = smallest distance from a correctly placed answer to the
        threshold it must stay on the right side of."""
        c = 0.0
        margin = high - low
        for value, want in pts:
            got = 2 if value >= d else 1 if value >= e else 0
            if got != want:
                c += weight if got == 0 else 1.0
            elif want == 0:
                margin = min(margin, e - value)
            elif want == 2:
                margin = min(margin, value - d)
            else:
                margin = min(margin, value - e, d - value)
        return c, round(margin, 9)

    best: tuple[float, float, float, float] | None = None  # (cost, -margin, e, d)
    for i, e in enumerate(grid):
        for d in grid[i:]:
            c, m = evaluate_bands(e, d)
            key = (c, -m, e, d)
            # Lower cost, then larger margin; iteration order keeps lower thresholds on ties.
            if best is None or key[:2] < best[:2]:
                best = key
    assert best is not None
    return score(points, Bands(escalate_at=best[2], deny_at=best[3]), severity)
