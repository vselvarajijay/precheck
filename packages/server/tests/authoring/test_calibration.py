"""`pytest -k calibration`"""

from precheck.core.schema import Bands, Severity, Verdict
from precheck.server.authoring.calibration import Point, calibrate, cost, score

A, E, D = Verdict.allow, Verdict.escalate, Verdict.deny


def pts(*pairs: tuple[float, Verdict]) -> list[Point]:
    return [Point(value=v, expected=e) for v, e in pairs]


def test_calibration_separable_reaches_100_percent() -> None:
    points = pts((0.05, A), (0.1, A), (0.2, A), (0.45, E), (0.5, E), (0.8, D), (0.95, D))
    s = calibrate(points, Severity.medium)
    assert s.correct == s.total == 7 and s.cost == 0
    assert 0.2 < s.bands.escalate_at <= 0.45 and 0.5 < s.bands.deny_at <= 0.8


def test_calibration_tie_prefers_margin_then_safer_lower_escalate() -> None:
    # Any escalate_at in (0.2, 0.45] and deny_at in (0.5, 0.8] is perfect. Largest margin puts
    # escalate_at mid-gap (0.32/0.33 both give margin 0.12 -> the safer, lower one), and among
    # the deny_at values keeping that margin, the lowest.
    points = pts((0.2, A), (0.45, E), (0.5, E), (0.8, D))
    s = calibrate(points, Severity.low)
    assert s.bands == Bands(escalate_at=0.32, deny_at=0.62)


def test_calibration_two_classes_splits_the_gap_not_the_edge() -> None:
    # One allow at 0.03, one deny at 0.96: don't hug either answer.
    s = calibrate(pts((0.03, A), (0.96, D)), Severity.high)
    assert s.correct == 2
    assert 0.45 <= s.bands.escalate_at <= s.bands.deny_at <= 0.55


def test_calibration_overlap_weighted_optimum_avoids_false_allows() -> None:
    # An allow at 0.6 overlaps a deny at 0.55: blocking the allow (cost 1) beats allowing the
    # deny (cost 5 for high severity).
    points = pts((0.1, A), (0.6, A), (0.55, D), (0.9, D))
    s = calibrate(points, Severity.high)
    assert s.bands.deny_at <= 0.55
    assert s.cost == 1.0 and s.correct == 3
    # With low severity (false allow costs 1) both choices cost 1; the safer (lower) wins.
    assert calibrate(points, Severity.low).bands.deny_at <= 0.55


def test_calibration_escalate_band_absorbs_uncertainty() -> None:
    points = pts((0.1, A), (0.3, A), (0.5, E), (0.55, E), (0.9, D))
    s = calibrate(points, Severity.medium)
    assert s.correct == 5
    assert s.bands.verdict(0.5) is E and s.bands.verdict(0.9) is D and s.bands.verdict(0.3) is A


def test_calibration_score_scale() -> None:
    points = pts((0.4, A), (1.2, A), (2.6, E), (3.7, D))
    s = calibrate(points, Severity.medium, low=0, high=4, step=0.05)
    assert s.correct == 4 and s.bands.escalate_at <= 2.6 and s.bands.deny_at <= 3.7


def test_calibration_cost_function() -> None:
    assert (
        cost(D, A, Severity.high) == 5
        and cost(E, A, Severity.medium) == 3
        and cost(D, A, Severity.low) == 1
    )
    assert (
        cost(A, D, Severity.high) == 1
        and cost(D, E, Severity.high) == 1
        and cost(E, E, Severity.high) == 0
    )
    assert score(pts((0.9, A)), Bands(escalate_at=0.4, deny_at=0.7), Severity.high).cost == 1
