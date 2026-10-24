from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.roof import RoofClass


class AlbedoGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    albedo_range: list[float]
    mean_c: float
    median_c: float
    std_c: float
    mean_area_m2: float
    centroid: list[float]


class SatelliteCase(BaseModel):
    """One roof set seen by one thermal instrument. Extra statistics (t_statistic,
    confounders, ...) are passed through as generated."""

    model_config = ConfigDict(extra="allow")

    case_id: str
    roof_class: RoofClass
    instrument: str
    instrument_resolution_m: float
    mean_roof_area_m2: float
    roof_to_pixel_area_ratio: float
    n_low: int
    n_high: int
    low_albedo_group: AlbedoGroup
    high_albedo_group: AlbedoGroup
    delta_c: float
    p_value: float
    significant: bool
    significant_raw: bool
    significant_bonferroni: bool
    significant_fdr: bool
    interpretation: str
    resolution_caveat: str


class SatelliteConclusion(BaseModel):
    """Presentation text; the counts let a client show the correction without parsing it."""

    model_config = ConfigDict(extra="allow")

    n_cases_tested: int
    n_significant_raw: int
    n_significant_bonferroni: int
    n_significant_fdr: int
    surviving_case_ids: list[str]
    untested_explanations: list[str]
    verdict: str
    text: str


class SatelliteEvidence(BaseModel):
    """Real, measured evidence only; produced by scripts/satellite_evidence.py."""

    model_config = ConfigDict(extra="allow")

    source: Literal["measured"]
    data_source: Literal["measured"]
    period: str
    # Headline case, flattened as the API contract describes it.
    instrument: str
    instrument_resolution_m: float
    low_albedo_group: AlbedoGroup
    high_albedo_group: AlbedoGroup
    delta_c: float
    p_value: float
    significant: bool
    resolution_caveat: str
    n_tests: int
    bonferroni_alpha: float
    multiple_comparison_note: str
    cases: list[SatelliteCase] = Field(min_length=1)
    conclusion: SatelliteConclusion
    caveat: str


class MetricsReport(BaseModel):
    """Method metrics on simulated data; produced by scripts/metrics.py. The nested
    tables are passed through as generated so the frontend sees every column."""

    model_config = ConfigDict(extra="allow")

    data_source: Literal["simulated"]
    generated_at: str
    anomaly_detection: dict
    normalization: dict


ClimateMethod = Literal["demand_weighted", "solar_only"]


class SeasonalBalance(BaseModel):
    model_config = ConfigDict(extra="allow")

    cooling_benefit_kwh_per_m2: float
    heating_penalty_kwh_per_m2: float
    net_benefit_kwh_per_m2: float
    penalty_to_benefit_ratio: float | None


class CityClimate(BaseModel):
    """Seasonal energy balance for one city under both framings; net_benefit_kwh_per_m2 is
    the primary (demand-weighted) value. Extra detail is passed through as generated."""

    model_config = ConfigDict(extra="allow")

    city: str
    summer_surface_cooling_c: float
    heating_degree_hours: float
    cooling_degree_hours: float
    net_benefit_kwh_per_m2: float
    heat_reference: dict
    demand_weighted: SeasonalBalance
    solar_only: SeasonalBalance


class ClimateComparison(BaseModel):
    """Rough physical estimate, not measured: data_source is always simulated."""

    model_config = ConfigDict(extra="allow")

    data_source: Literal["simulated"]
    primary_method: ClimateMethod
    secondary_method: ClimateMethod
    secondary_method_note: str
    cities: list[CityClimate] = Field(min_length=1)
    conclusion: str
    assumptions: list[str] = Field(min_length=1)
    method: str
    caveat: str
