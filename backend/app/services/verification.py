"""Joins every verification step for one roof: measurements, weather, normalisation,
anomaly detection, coverage, force majeure, decision, evidence and signature."""

from dataclasses import dataclass

from app.repositories.transactions import RepositoryContext

from app.core.config import thresholds_for
from app.core.exceptions import MissingMeasurementError, RoofNotFoundError, WeatherUnavailableError
from app.repositories.records import MeasurementData, WeatherData, RoofData, roof_data
from app.repositories import measurements as measurement_repo
from app.repositories import roofs as roof_repo
from app.repositories import verifications as verification_repo
from app.schemas.verification import VerificationResult, WeatherConditions
from app.services import analysis, evidence, weather
from app.services.decision import Decision, WeatherExtremes, decide
from app.services.photos import CoverageOutcome, evaluate_coverage

DELTA_DECIMALS = 2


@dataclass(frozen=True)
class MeasurementContext:
    measurement: MeasurementData
    window: list[WeatherData]
    at_plateau: WeatherData


def _require_measurement(
    db: RepositoryContext, roof_id: str, phases: tuple[str, ...], label: str
) -> MeasurementData:
    measurement = measurement_repo.latest_data(db, roof_id, phases)
    if measurement is None:
        raise MissingMeasurementError(roof_id, label)
    return measurement


def _load_context(db: RepositoryContext, measurement: MeasurementData) -> MeasurementContext:
    times = analysis.reading_times(measurement)
    start, end = weather.measurement_window(min(times), max(times))
    records = weather.ensure_weather(db, measurement.roof_id, start, end)
    at_plateau = weather.nearest_record(records, max(times))
    if at_plateau is None:
        raise WeatherUnavailableError(f"No weather data for measurement {measurement.id}.")
    return MeasurementContext(measurement, records, at_plateau)


def _merge_unique(*flag_lists: list[str]) -> list[str]:
    return list(dict.fromkeys(flag for flags in flag_lists for flag in flags))


def _detect_all_flags(
    db: RepositoryContext, before: MeasurementContext, after: MeasurementContext, delta_c: float
) -> list[str]:
    """The baseline is checked too: a frozen or replayed before-measurement would
    invalidate the comparison just as much as a bad after-measurement."""
    flags = []
    for context, context_delta in ((before, None), (after, delta_c)):
        upload = context.measurement
        others = measurement_repo.list_other_device_uploads(db, upload.device_id, upload.id)
        weather_now = analysis.to_ml_weather(context.at_plateau)
        flags.append(analysis.detect_flags(upload, weather_now, context_delta, others))
    return _merge_unique(*flags)


def _weather_extremes(after: MeasurementContext) -> WeatherExtremes:
    records = after.window
    return WeatherExtremes(
        max_gust_ms=max(record.max_gust_ms for record in records),
        total_precipitation_mm=sum(record.precipitation_mm for record in records),
    )


def _measurement_evidence(measurement: MeasurementData) -> dict:
    return {
        "measurement_id": str(measurement.id),
        "roof_id": measurement.roof_id,
        "phase": measurement.phase,
        "device_id": measurement.device_id,
        "measured_at": measurement.measured_at.isoformat(),
        "raw_readings": measurement.raw_readings,
    }


def _weather_evidence(record: WeatherData) -> dict:
    """The provenance label is left out so evidence hashes stay comparable with
    verifications recorded before weather rows were labelled."""
    point = weather.to_weather_point(record)
    return point.model_dump(mode="json", exclude={"data_source"})


def _evidence_hash(
    before: MeasurementContext, after: MeasurementContext, coverage: CoverageOutcome
) -> str:
    measurements = [
        _measurement_evidence(before.measurement),
        _measurement_evidence(after.measurement),
    ]
    records = sorted(
        {r.id: r for r in (*before.window, *after.window)}.values(), key=lambda r: r.timestamp
    )
    return evidence.compute_evidence_hash(
        measurements, coverage.photo_bytes, [_weather_evidence(r) for r in records]
    )


def _build_result(
    roof: RoofData,
    after: MeasurementContext,
    measured_delta_c: float,
    normalized_delta_c: float,
    coverage: CoverageOutcome,
    decision: Decision,
    evidence_hash: str,
) -> VerificationResult:
    plateau = after.at_plateau
    return VerificationResult(
        roof_id=roof.id,
        measurement_id=after.measurement.id,
        measurement_phase=after.measurement.phase,
        status=decision.status,
        measured_delta_c=round(measured_delta_c, DELTA_DECIMALS),
        normalized_delta_c=round(normalized_delta_c, DELTA_DECIMALS),
        coverage_pct=coverage.coverage_pct,
        anomaly_flags=list(decision.anomaly_flags),
        force_majeure=decision.force_majeure,
        weather=WeatherConditions(
            ambient_c=plateau.ambient_c,
            radiation_wm2=plateau.radiation_wm2,
            wind_ms=plateau.wind_ms,
            max_gust_ms=max(record.max_gust_ms for record in after.window),
            precipitation_mm=_weather_extremes(after).total_precipitation_mm,
            window_start=min(record.timestamp for record in after.window),
            window_end=max(record.timestamp for record in after.window) + weather.HOUR,
        ),
        evidence_hash=evidence_hash,
        device_signature=evidence.sign_evidence(evidence_hash),
        measured_at=after.measurement.measured_at,
        reason=decision.reason,
        data_source=after.measurement.data_source,
    )


def _refresh_coverage(after: MeasurementData) -> CoverageOutcome:
    """Runs before normalisation, which weights the after-albedo by coverage; a freshly
    analysed photo also refreshes the stored value."""
    coverage = evaluate_coverage(after)
    if coverage.photo_bytes:
        after.coverage_pct = coverage.coverage_pct
    return coverage


def verify_roof(db: RepositoryContext, roof_id: str) -> VerificationResult:
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    roof = roof_data(located.roof)
    before_measurement = _require_measurement(db, roof_id, (analysis.BEFORE_PHASE,), "before")
    after_measurement = _require_measurement(db, roof_id, analysis.POST_COATING_PHASES, "after")
    analysis.require_same_source(before_measurement, after_measurement.data_source)
    before = _load_context(db, before_measurement)
    after = _load_context(db, after_measurement)
    measured_delta_c = analysis.plateau_temp(after.measurement) - analysis.plateau_temp(
        before.measurement
    )
    coverage = _refresh_coverage(after.measurement)
    normalized_delta_c = analysis.normalized_delta(
        roof,
        before.measurement,
        after.measurement,
        analysis.to_ml_weather(before.at_plateau),
        analysis.to_ml_weather(after.at_plateau),
    )
    ml_flags = _detect_all_flags(db, before, after, measured_delta_c)
    decision = decide(
        normalized_delta_c,
        coverage,
        ml_flags,
        _weather_extremes(after),
        thresholds_for(roof.city),
    )
    result = _build_result(
        roof,
        after,
        measured_delta_c,
        normalized_delta_c,
        coverage,
        decision,
        _evidence_hash(before, after, coverage),
    )
    verification_repo.save_result(db, result, after.measurement, ml_flags)
    return result
