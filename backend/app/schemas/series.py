from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SimulatedReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    surface_temp_c: float
    data_source: Literal["simulated"]


class SimulatedPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    albedo: float
    readings: list[SimulatedReading]


class SimulatedSeriesResponse(BaseModel):
    """Physical-model output driven by real Open-Meteo weather. The weather is real,
    the surface temperatures are not: data_source is always simulated."""

    model_config = ConfigDict(extra="forbid")

    roof_id: str
    data_source: Literal["simulated"]
    model: str
    weather_source: str
    before: SimulatedPhase
    after: SimulatedPhase
