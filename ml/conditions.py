"""Value types shared by the physical model, the synthetic series and normalisation.

Kept in their own module so those three can exchange data without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MIN_ALBEDO = 0.0
MAX_ALBEDO = 1.0


class InvalidObservationError(ValueError):
    """Raised when an input lies outside the physically meaningful range."""


@dataclass(frozen=True)
class Weather:
    ambient_c: float
    radiation_wm2: float
    wind_ms: float


@dataclass(frozen=True)
class Reading:
    """measured_at only orders readings and measures gaps between them; ml never derives
    the sun's position from it, so its timezone does not matter here."""

    measured_at: datetime
    surface_temp_c: float


@dataclass(frozen=True)
class RoofObservation:
    """local_hour is the LOCAL clock hour (0-24) at the roof when the reading was taken.
    It is a separate field, not derived from reading.measured_at, because ml knows no
    timezones: the caller converts from UTC, and a UTC hour passed here by mistake would
    shift the sun correction by the timezone offset."""

    reading: Reading
    weather: Weather
    albedo: float
    local_hour: float


@dataclass(frozen=True)
class MeasurementSession:
    """One device upload: the probe curve, the weather during it, and its delta to the
    roof's previous measurement (None when there is no earlier measurement)."""

    device_id: str
    readings: tuple[Reading, ...]
    weather: Weather | None
    delta_c: float | None


def clock_hour(moment: datetime) -> float:
    """Fractional hour of a datetime already expressed in the roof's local time."""
    return moment.hour + moment.minute / 60 + moment.second / 3600


def validate_albedo(albedo: float) -> None:
    if not MIN_ALBEDO <= albedo <= MAX_ALBEDO:
        raise InvalidObservationError(
            f"albedo must be within [{MIN_ALBEDO}, {MAX_ALBEDO}], got {albedo}."
        )
