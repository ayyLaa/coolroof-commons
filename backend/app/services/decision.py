"""Pure verification rules: status, force majeure and the human-readable reason.

Free of database and HTTP so every branch that can move or lock funds is unit-tested.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import Thresholds
from app.services.photos import CoverageOutcome

# Flags that say data is missing rather than suspicious: they lead to
# insufficient_data, not to a flagged result that would blame the contractor.
DATA_GAP_FLAGS = frozenset({"too_few_readings", "missing_weather"})
EXTREME_WIND_FLAG = "extreme_wind_event"
HEAVY_PRECIPITATION_FLAG = "heavy_precipitation"
DELTA_THRESHOLD_FLAG = "normalized_delta_below_threshold"
COVERAGE_THRESHOLD_FLAG = "coverage_below_threshold"


@dataclass(frozen=True)
class WeatherExtremes:
    max_gust_ms: float
    total_precipitation_mm: float


@dataclass(frozen=True)
class Decision:
    status: str
    anomaly_flags: tuple[str, ...]
    force_majeure: bool
    reason: str


def force_majeure_flags(extremes: WeatherExtremes, thresholds: Thresholds) -> list[str]:
    flags = []
    if extremes.max_gust_ms > thresholds.force_majeure_gust_ms:
        flags.append(EXTREME_WIND_FLAG)
    if extremes.total_precipitation_mm > thresholds.force_majeure_precip_mm:
        flags.append(HEAVY_PRECIPITATION_FLAG)
    return flags


def threshold_flags(
    normalized_delta_c: float, coverage_pct: float, thresholds: Thresholds
) -> list[str]:
    flags = []
    if normalized_delta_c > thresholds.min_normalized_delta_c:
        flags.append(DELTA_THRESHOLD_FLAG)
    if coverage_pct < thresholds.min_coverage_pct:
        flags.append(COVERAGE_THRESHOLD_FLAG)
    return flags


def _force_majeure_reason(extremes: WeatherExtremes, thresholds: Thresholds) -> str:
    return (
        f"Weather during the measurement window exceeded force majeure limits (max gust "
        f"{extremes.max_gust_ms:.1f} m/s vs {thresholds.force_majeure_gust_ms:.1f} m/s, total "
        f"precipitation {extremes.total_precipitation_mm:.1f} mm vs "
        f"{thresholds.force_majeure_precip_mm:.1f} mm). Storm conditions make the thermal "
        "measurement unreliable, so the result is insufficient_data; the escrow separately checks reserve eligibility."
    )


def _anomaly_reason(flags: Sequence[str]) -> str:
    return (
        f"Anomalies detected in the measurement ({', '.join(flags)}). "
        "Automatic approval is withheld and the case goes to manual review."
    )


def _insufficient_reason(gaps: Sequence[str], coverage: CoverageOutcome) -> str:
    problems = [f"data gap: {gap}" for gap in gaps]
    if not coverage.reliable:
        issues = ", ".join(coverage.quality_issues) or "low confidence"
        problems.append(
            f"coverage photo not usable ({issues}, confidence {coverage.confidence:.2f})"
        )
    summary = "; ".join(problems)
    return f"Not enough reliable evidence to decide: {summary}. A new measurement is needed."


def _threshold_reason(
    normalized_delta_c: float, coverage_pct: float, missed: Sequence[str], thresholds: Thresholds
) -> str:
    delta = (
        f"Normalized temperature change ({normalized_delta_c:.1f}C) "
        f"{'does not reach' if DELTA_THRESHOLD_FLAG in missed else 'meets'} the "
        f"{thresholds.min_normalized_delta_c:.1f}C threshold"
    )
    coverage = (
        f"coating coverage ({coverage_pct:.1f}%) "
        f"{'is below' if COVERAGE_THRESHOLD_FLAG in missed else 'meets'} the required "
        f"{thresholds.min_coverage_pct:.0f}%"
    )
    # The winter check only annotates the reason and never changes the status: the heating
    # penalty is a rough simulated estimate (insulation and heating use unknown), not
    # reliable enough to block a payout the measured evidence has earned.
    if not missed and thresholds.winter_penalty_check:
        return (
            f"{delta} and {coverage}. No anomalies detected; funds can be released. Note: "
            "this climate has a real heating season, so the coating also carries a winter "
            "heating penalty; that estimate is shown for context only and does not block "
            "payout (see /evidence/climate-comparison)."
        )
    if not missed:
        return f"{delta} and {coverage}. No anomalies detected; funds can be released."
    return f"{delta} and {coverage}. Routed to manual review instead of automatic approval."


def decide(
    normalized_delta_c: float,
    coverage: CoverageOutcome,
    ml_flags: Sequence[str],
    extremes: WeatherExtremes,
    thresholds: Thresholds,
) -> Decision:
    """Order matters: force majeure first, because storm noise would otherwise surface
    as anomalies and blame the contractor; then suspicious data; then missing data;
    only clean, complete evidence is judged against the thresholds."""
    weather_flags = force_majeure_flags(extremes, thresholds)
    if weather_flags:
        reason = _force_majeure_reason(extremes, thresholds)
        return Decision("insufficient_data", (*ml_flags, *weather_flags), True, reason)
    suspicious = [flag for flag in ml_flags if flag not in DATA_GAP_FLAGS]
    if suspicious:
        return Decision("flagged", tuple(ml_flags), False, _anomaly_reason(suspicious))
    gaps = [flag for flag in ml_flags if flag in DATA_GAP_FLAGS]
    if gaps or not coverage.reliable:
        return Decision(
            "insufficient_data", tuple(ml_flags), False, _insufficient_reason(gaps, coverage)
        )
    missed = threshold_flags(normalized_delta_c, coverage.coverage_pct, thresholds)
    reason = _threshold_reason(normalized_delta_c, coverage.coverage_pct, missed, thresholds)
    return Decision("flagged" if missed else "approved", tuple(missed), False, reason)
