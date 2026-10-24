import pytest

from app.core.config import DEFAULT_THRESHOLDS as THRESHOLDS
from app.core.config import thresholds_for
from app.services.decision import (
    COVERAGE_THRESHOLD_FLAG,
    DELTA_THRESHOLD_FLAG,
    EXTREME_WIND_FLAG,
    HEAVY_PRECIPITATION_FLAG,
    WeatherExtremes,
    decide,
)
from app.services.photos import NO_PHOTO, CoverageOutcome

CALM = WeatherExtremes(max_gust_ms=6.0, total_precipitation_mm=0.0)
GOOD_COVERAGE = CoverageOutcome(94.5, 1.0, True, (), b"")
GOOD_DELTA_C = -12.0


def test_clean_evidence_is_approved() -> None:
    decision = decide(GOOD_DELTA_C, GOOD_COVERAGE, [], CALM, THRESHOLDS)

    assert decision.status == "approved"
    assert decision.anomaly_flags == ()
    assert "funds can be released" in decision.reason


@pytest.mark.parametrize(
    ("delta_c", "coverage_pct", "expected_flags"),
    [
        (-3.0, 94.5, (DELTA_THRESHOLD_FLAG,)),
        (-12.0, 61.0, (COVERAGE_THRESHOLD_FLAG,)),
        (-3.0, 61.0, (DELTA_THRESHOLD_FLAG, COVERAGE_THRESHOLD_FLAG)),
    ],
)
def test_missed_thresholds_are_flagged(
    delta_c: float, coverage_pct: float, expected_flags: tuple[str, ...]
) -> None:
    coverage = CoverageOutcome(coverage_pct, 1.0, True, (), b"")

    decision = decide(delta_c, coverage, [], CALM, THRESHOLDS)

    assert decision.status == "flagged"
    assert decision.anomaly_flags == expected_flags


def test_delta_exactly_at_threshold_is_approved() -> None:
    decision = decide(THRESHOLDS.min_normalized_delta_c, GOOD_COVERAGE, [], CALM, THRESHOLDS)

    assert decision.status == "approved"


def test_force_majeure_wins_over_everything() -> None:
    storm = WeatherExtremes(max_gust_ms=24.0, total_precipitation_mm=68.0)

    decision = decide(GOOD_DELTA_C, GOOD_COVERAGE, ["statistical_outlier"], storm, THRESHOLDS)

    assert decision.status == "insufficient_data"
    assert decision.force_majeure is True
    assert decision.anomaly_flags == (
        "statistical_outlier",
        EXTREME_WIND_FLAG,
        HEAVY_PRECIPITATION_FLAG,
    )


def test_suspicious_anomaly_is_flagged_even_with_data_gaps() -> None:
    decision = decide(GOOD_DELTA_C, GOOD_COVERAGE, ["replay", "too_few_readings"], CALM, THRESHOLDS)

    assert decision.status == "flagged"
    assert "replay" in decision.reason


def test_data_gap_is_insufficient_data() -> None:
    decision = decide(GOOD_DELTA_C, GOOD_COVERAGE, ["too_few_readings"], CALM, THRESHOLDS)

    assert decision.status == "insufficient_data"
    assert decision.force_majeure is False


def test_missing_photo_is_insufficient_data() -> None:
    decision = decide(GOOD_DELTA_C, NO_PHOTO, [], CALM, THRESHOLDS)

    assert decision.status == "insufficient_data"
    assert "no_photo" in decision.reason


def test_low_confidence_photo_is_insufficient_data() -> None:
    dark = CoverageOutcome(94.0, 0.35, False, ("too_dark",), b"")

    decision = decide(GOOD_DELTA_C, dark, [], CALM, THRESHOLDS)

    assert decision.status == "insufficient_data"
    assert "too_dark" in decision.reason


def test_london_approval_mentions_winter_penalty() -> None:
    decision = decide(-6.5, GOOD_COVERAGE, [], CALM, thresholds_for("London"))

    assert decision.status == "approved"
    assert "winter heating penalty" in decision.reason
    assert "does not block payout" in decision.reason


def test_winter_check_does_not_change_a_flagged_status() -> None:
    decision = decide(-3.0, GOOD_COVERAGE, [], CALM, thresholds_for("London"))

    assert decision.status == "flagged"
    assert "winter heating penalty" not in decision.reason


def test_athens_threshold_rejects_what_london_accepts() -> None:
    assert decide(-6.5, GOOD_COVERAGE, [], CALM, thresholds_for("Athens")).status == "flagged"
