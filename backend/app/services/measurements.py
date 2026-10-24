from uuid import UUID

from app.repositories.transactions import RepositoryContext, commit

from app.core.exceptions import (
    MeasurementNotFoundError,
    MissingMeasurementError,
    RoofNotFoundError,
    WeatherUnavailableError,
)
from app.models import Measurement, WeatherRecord
from app.repositories import measurements as measurement_repo
from app.repositories import roofs as roof_repo
from app.schemas.measurement import (
    MeasurementCreateRequest,
    MeasurementCreateResponse,
    MeasurementPhase,
    PhotoUploadResponse,
)
from app.services import analysis, photos, weather

# The API contract requires a number; a before-measurement has no reference to differ
# from, so its delta is reported as zero while the stored value stays NULL.
NO_REFERENCE_DELTA_C = 0.0


def _build_measurement(payload: MeasurementCreateRequest) -> Measurement:
    readings = sorted(payload.readings, key=lambda reading: reading.timestamp)
    return Measurement(
        roof_id=payload.roof_id,
        phase=payload.phase.value,
        device_id=payload.device_id,
        raw_readings=[reading.model_dump(mode="json") for reading in readings],
        measured_at=readings[0].timestamp,
        anomaly_flags=[],
        data_source=payload.data_source,
    )


def _weather_at_plateau(db: RepositoryContext, measurement: Measurement) -> WeatherRecord | None:
    """Intake never fails on weather: a missing record becomes the missing_weather flag,
    and verification later insists on real data."""
    times = analysis.reading_times(measurement)
    start, end = weather.measurement_window(min(times), max(times))
    try:
        records = weather.ensure_weather(db, measurement.roof_id, start, end)
    except WeatherUnavailableError:
        return None
    return weather.nearest_record(records, max(times))


def _reference_measurement(db: RepositoryContext, payload: MeasurementCreateRequest) -> Measurement | None:
    if payload.phase == MeasurementPhase.BEFORE:
        return None
    before = measurement_repo.latest_measurement(db, payload.roof_id, (analysis.BEFORE_PHASE,))
    if before is None:
        raise MissingMeasurementError(payload.roof_id, analysis.BEFORE_PHASE)
    analysis.require_same_source(before, payload.data_source)
    return before


def _normalized_delta(
    db: RepositoryContext,
    located: roof_repo.RoofWithLocation,
    before: Measurement,
    after: Measurement,
    after_weather: WeatherRecord | None,
) -> float | None:
    before_weather = _weather_at_plateau(db, before)
    if before_weather is None or after_weather is None:
        return None
    return analysis.normalized_delta(
        located.roof,
        before,
        after,
        analysis.to_ml_weather(before_weather),
        analysis.to_ml_weather(after_weather),
    )


def create_measurement(db: RepositoryContext, payload: MeasurementCreateRequest) -> MeasurementCreateResponse:
    located = roof_repo.get_roof(db, payload.roof_id)
    if located is None:
        raise RoofNotFoundError(payload.roof_id)
    before = _reference_measurement(db, payload)
    measurement = measurement_repo.add_measurement(db, _build_measurement(payload))
    plateau_weather = _weather_at_plateau(db, measurement)
    raw_delta = None
    if before is not None:
        raw_delta = analysis.plateau_temp(measurement) - analysis.plateau_temp(before)
        measurement.normalized_delta_c = _normalized_delta(
            db, located, before, measurement, plateau_weather
        )
    others = measurement_repo.list_other_device_uploads(db, measurement.device_id, measurement.id)
    measurement.anomaly_flags = analysis.detect_flags(
        measurement, analysis.to_ml_weather(plateau_weather), raw_delta, others
    )
    commit(db)
    delta = measurement.normalized_delta_c
    return MeasurementCreateResponse(
        measurement_id=str(measurement.id),
        normalized_delta_c=NO_REFERENCE_DELTA_C if delta is None else round(delta, 2),
        anomaly_flags=measurement.anomaly_flags,
        data_source=measurement.data_source,
    )


def _get_measurement(db: RepositoryContext, measurement_id: str) -> Measurement:
    try:
        measurement = measurement_repo.get_measurement(db, UUID(measurement_id))
    except ValueError:
        measurement = None
    if measurement is None:
        raise MeasurementNotFoundError(measurement_id)
    return measurement


def upload_photo(
    db: RepositoryContext, measurement_id: str, filename: str, content: bytes
) -> PhotoUploadResponse:
    measurement = _get_measurement(db, measurement_id)
    photo_path = photos.save_photo(str(measurement.id), filename, content)
    report = photos.run_coverage(photo_path)
    measurement.photo_path = photos.to_stored_path(photo_path)
    measurement.coverage_pct = report["coverage_pct"]
    commit(db)
    return PhotoUploadResponse(
        coverage_pct=report["coverage_pct"],
        mask_preview_url=photos.mask_preview_url(report["mask_path"]),
    )
