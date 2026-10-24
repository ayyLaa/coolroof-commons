from app.repositories.transactions import RepositoryContext

from app.core.config import COST_PER_M2_EUR
from app.core.exceptions import RoofNotFoundError
from app.models import Measurement
from app.repositories import measurements as measurement_repo
from app.repositories import roofs as roof_repo
from app.repositories.roofs import RoofWithLocation
from app.schemas.measurement import MeasurementPhase
from app.schemas.roof import MeasurementHistoryEntry, RoofDetail, RoofSummary

EUR_DECIMALS = 2


def estimate_cost_eur(area_m2: float) -> float:
    return round(area_m2 * COST_PER_M2_EUR, EUR_DECIMALS)


def to_summary(located: RoofWithLocation) -> RoofSummary:
    roof = located.roof
    return RoofSummary(
        roof_id=roof.id,
        city=roof.city,
        roof_class=roof.roof_class,
        lat=located.lat,
        lon=located.lon,
        area_m2=roof.area_m2,
        albedo=roof.albedo,
        surface_temp_c=roof.surface_temp_c,
        priority_score=roof.priority_score,
        estimated_cost_eur=estimate_cost_eur(roof.area_m2),
        status=roof.status,
        data_source=roof.data_source,
        geometry=located.geometry,
    )


def to_history_entry(measurement: Measurement) -> MeasurementHistoryEntry:
    return MeasurementHistoryEntry(
        measurement_id=str(measurement.id),
        phase=MeasurementPhase(measurement.phase),
        measured_at=measurement.measured_at,
        normalized_delta_c=measurement.normalized_delta_c,
        anomaly_flags=measurement.anomaly_flags or [],
        data_source=measurement.data_source,
    )


def list_roofs(
    db: RepositoryContext,
    city: str | None,
    page: tuple[int, int],
    min_score: float | None,
    include_geometry: bool,
) -> list[RoofSummary]:
    """Footprints are opt-in on the list: they more than double each entry, and the
    centroid in lat/lon is enough to place a marker."""
    located = roof_repo.list_roofs(db, city, min_score, page, include_geometry)
    return [to_summary(roof) for roof in located]


def get_roof_detail(db: RepositoryContext, roof_id: str) -> RoofDetail:
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    history = [to_history_entry(m) for m in measurement_repo.list_for_roof(db, roof_id)]
    return RoofDetail(**to_summary(located).model_dump(), measurement_history=history)
