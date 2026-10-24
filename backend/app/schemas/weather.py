from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.data_source import DataSource


class WeatherPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    ambient_c: float
    radiation_wm2: float = Field(ge=0)
    wind_ms: float = Field(ge=0)
    max_gust_ms: float = Field(ge=0)
    precipitation_mm: float = Field(ge=0)
    data_source: DataSource
