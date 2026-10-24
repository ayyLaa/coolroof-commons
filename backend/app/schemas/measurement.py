from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.data_source import DataSource, MeasurementSource


class MeasurementPhase(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    DURABILITY = "durability"


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    surface_temp_c: float


class MeasurementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roof_id: str
    phase: MeasurementPhase
    readings: list[Reading] = Field(min_length=1)
    device_id: str
    # No physical experiment runs in this project, so uploads default to simulated;
    # a real field device would send "measured".
    data_source: MeasurementSource = "simulated"


class MeasurementCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_id: str
    normalized_delta_c: float
    anomaly_flags: list[str] = Field(default_factory=list)
    data_source: DataSource


class PhotoUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_pct: float = Field(ge=0, le=100)
    mask_preview_url: str
