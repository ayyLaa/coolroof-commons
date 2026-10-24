from dataclasses import dataclass, fields
from datetime import datetime
from uuid import UUID


@dataclass
class MeasurementData:
    id: UUID
    roof_id: str
    phase: str
    device_id: str
    raw_readings: list[dict]
    measured_at: datetime
    data_source: str
    coverage_pct: float | None
    normalized_delta_c: float | None
    anomaly_flags: list[str]
    photo_path: str | None


@dataclass(frozen=True)
class WeatherData:
    id: UUID
    roof_id: str
    timestamp: datetime
    ambient_c: float
    radiation_wm2: float
    wind_ms: float
    max_gust_ms: float
    precipitation_mm: float
    data_source: str


@dataclass(frozen=True)
class RoofData:
    id: str
    city: str
    timezone: str
    albedo: float


def measurement_data(row: object) -> MeasurementData:
    return MeasurementData(**{field.name: getattr(row, field.name) for field in fields(MeasurementData)})


def weather_data(row: object) -> WeatherData:
    return WeatherData(**{field.name: getattr(row, field.name) for field in fields(WeatherData)})


def roof_data(row: object) -> RoofData:
    return RoofData(**{field.name: getattr(row, field.name) for field in fields(RoofData)})
