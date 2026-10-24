from pydantic import BaseModel, ConfigDict, Field


class DemoDeletedRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Only a new round clears these: they mirror the previous round's projects.
    contract_events: int = Field(ge=0)
    contract_states: int = Field(ge=0)
    verifications: int = Field(ge=0)
    measurements: int = Field(ge=0)
    weather_records: int = Field(ge=0)
    photo_files: int = Field(ge=0)


class DemoRestoredRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roofs: int = Field(ge=0)
    measurements: int = Field(ge=0)
    verifications: int = Field(ge=0)
    weather_records: int = Field(ge=0)
    # Pending tranches created where none existed; tranches already on file are kept.
    contract_states: int = Field(ge=0)


class DemoRoundStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=0)


class DemoResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=0)
    roof_ids: list[str]
    deleted: DemoDeletedRows
    restored: DemoRestoredRows
