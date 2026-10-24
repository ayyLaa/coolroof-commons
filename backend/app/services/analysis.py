"""Translates stored measurements and weather into ml/ inputs and back.

Both measurement intake and verification run the same normalisation and anomaly
checks; keeping the translation here means they can never disagree on, e.g., which
readings form the plateau or which albedo a phase uses.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from statistics import fmean

from ml.anomaly import assess_measurement
from ml.conditions import MeasurementSession, RoofObservation, clock_hour
from ml.conditions import Reading as MlReading
from ml.conditions import Weather as MlWeather
from ml.normalization import compute_normalized_delta

from app.core import timezones
from app.core.config import ASSUMED_COATED_ALBEDO
from app.core.exceptions import MixedDataSourceError
from app.repositories.records import MeasurementData, RoofData, WeatherData

# The probe settles within the 15-minute window; the last readings are its plateau.
PLATEAU_SAMPLE_SIZE = 3
BEFORE_PHASE = "before"
POST_COATING_PHASES = ("after", "durability")
PERCENT = 100.0


def require_same_source(reference: MeasurementData, data_source: str) -> str:
    """A delta between a measured and a simulated value would mean nothing, and would
    let simulated numbers pass as real ones; such comparisons are refused outright."""
    if reference.data_source != data_source:
        raise MixedDataSourceError(
            f"Cannot compare a {data_source} measurement with the {reference.data_source} "
            f"{reference.phase} measurement {reference.id}."
        )
    return data_source


def parse_timestamp(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def reading_times(measurement: MeasurementData) -> list[datetime]:
    return [parse_timestamp(reading["timestamp"]) for reading in measurement.raw_readings]


def plateau_temp(measurement: MeasurementData) -> float:
    temps = [reading["surface_temp_c"] for reading in measurement.raw_readings]
    return fmean(temps[-PLATEAU_SAMPLE_SIZE:])


def local_hour(moment: datetime, roof: RoofData) -> float:
    """The single place where a stored UTC instant becomes the local hour ml expects."""
    return clock_hour(timezones.to_local(moment, roof.timezone))


def to_ml_readings(measurement: MeasurementData) -> tuple[MlReading, ...]:
    """Kept in UTC: anomaly checks only order readings and measure gaps."""
    return tuple(
        MlReading(measured_at=parse_timestamp(r["timestamp"]), surface_temp_c=r["surface_temp_c"])
        for r in measurement.raw_readings
    )


def to_ml_weather(record: WeatherData | None) -> MlWeather | None:
    if record is None:
        return None
    return MlWeather(
        ambient_c=record.ambient_c, radiation_wm2=record.radiation_wm2, wind_ms=record.wind_ms
    )


def phase_albedo(roof: RoofData, measurement: MeasurementData) -> float:
    """Before the coating the roof's satellite albedo applies. Afterwards the albedo is
    area-weighted by measured coverage: assuming a fully coated roof would credit a
    half-painted one with the full coating's sensitivity and inflate its normalised gain."""
    if measurement.phase == BEFORE_PHASE:
        return roof.albedo
    if measurement.coverage_pct is None:
        return ASSUMED_COATED_ALBEDO
    coated_share = measurement.coverage_pct / PERCENT
    return roof.albedo + coated_share * (ASSUMED_COATED_ALBEDO - roof.albedo)


def to_observation(measurement: MeasurementData, weather: MlWeather, roof: RoofData) -> RoofObservation:
    plateau_at = reading_times(measurement)[-1]
    return RoofObservation(
        reading=MlReading(measured_at=plateau_at, surface_temp_c=plateau_temp(measurement)),
        weather=weather,
        albedo=phase_albedo(roof, measurement),
        local_hour=local_hour(plateau_at, roof),
    )


def normalized_delta(
    roof: RoofData,
    before: MeasurementData,
    after: MeasurementData,
    before_weather: MlWeather,
    after_weather: MlWeather,
) -> float:
    return compute_normalized_delta(
        to_observation(before, before_weather, roof), to_observation(after, after_weather, roof)
    )


def to_session(
    measurement: MeasurementData, weather: MlWeather | None, delta_c: float | None
) -> MeasurementSession:
    return MeasurementSession(
        device_id=measurement.device_id,
        readings=to_ml_readings(measurement),
        weather=weather,
        delta_c=delta_c,
    )


def detect_flags(
    measurement: MeasurementData,
    weather: MlWeather | None,
    delta_c: float | None,
    other_uploads: Sequence[MeasurementData],
) -> list[str]:
    """Rule and statistical flags are merged here because the verification payload has
    a single anomaly_flags list; ml/anomaly keeps them apart for the comparison."""
    history = [to_session(upload, None, None) for upload in other_uploads]
    report = assess_measurement(to_session(measurement, weather, delta_c), history)
    return [flag.value for flag in (*report.rule_flags, *report.statistical_flags)]
