from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.data_source import DataSource
from app.schemas.measurement import MeasurementPhase
from app.schemas.verification import ROOF_ID_PATTERN

RoofClass = Literal["small", "large"]


class GeoJsonPolygon(BaseModel):
    """GeoJSON order: each position is [lon, lat]."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]


class RoofSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roof_id: str = Field(pattern=ROOF_ID_PATTERN)
    city: str
    roof_class: RoofClass
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    area_m2: float = Field(ge=0)
    albedo: float = Field(ge=0, le=1)
    surface_temp_c: float
    priority_score: float = Field(ge=0, le=1)
    estimated_cost_eur: float = Field(ge=0)
    status: str
    data_source: DataSource
    geometry: GeoJsonPolygon | None


class MeasurementHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_id: str
    phase: MeasurementPhase
    measured_at: datetime
    normalized_delta_c: float | None = None
    anomaly_flags: list[str] = Field(default_factory=list)
    data_source: DataSource


class RoofDetail(RoofSummary):
    geometry: GeoJsonPolygon
    measurement_history: list[MeasurementHistoryEntry]
