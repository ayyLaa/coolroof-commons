from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.data_source import DataSource

ROOF_ID_PATTERN = r"^[A-Z]{3}-[0-9]{4}$"
EVIDENCE_HASH_PATTERN = r"^0x[a-fA-F0-9]{64}$"
DEVICE_SIGNATURE_PATTERN = r"^0x[a-fA-F0-9]{130}$"

VerificationStatus = Literal["approved", "flagged", "insufficient_data"]


class WeatherConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient_c: float
    radiation_wm2: float = Field(ge=0)
    wind_ms: float = Field(ge=0)
    max_gust_ms: float = Field(ge=0)
    precipitation_mm: float = Field(ge=0)
    window_start: datetime
    window_end: datetime


class VerificationResult(BaseModel):
    """schema/verification.json plus data_source, which says whether the compared
    measurements were measured or simulated."""

    model_config = ConfigDict(extra="forbid")

    roof_id: str = Field(pattern=ROOF_ID_PATTERN, examples=["ATH-0142"])
    measurement_id: UUID
    measurement_phase: Literal["after", "durability"]
    status: VerificationStatus
    measured_delta_c: float
    normalized_delta_c: float
    coverage_pct: float = Field(ge=0, le=100)
    anomaly_flags: list[str] = Field(default_factory=list)
    force_majeure: bool
    weather: WeatherConditions
    evidence_hash: str = Field(pattern=EVIDENCE_HASH_PATTERN)
    device_signature: str = Field(pattern=DEVICE_SIGNATURE_PATTERN)
    measured_at: datetime
    reason: str
    data_source: DataSource
