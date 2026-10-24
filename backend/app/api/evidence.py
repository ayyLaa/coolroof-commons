from fastapi import APIRouter

from app.schemas.error import ErrorResponse
from app.schemas.evidence import ClimateComparison, MetricsReport, SatelliteEvidence
from app.services import evidence_reports

router = APIRouter(tags=["evidence"])


@router.get("/metrics", response_model=MetricsReport, responses={404: {"model": ErrorResponse}})
def get_metrics() -> MetricsReport:
    return evidence_reports.get_metrics()


@router.get(
    "/evidence/satellite",
    response_model=SatelliteEvidence,
    responses={404: {"model": ErrorResponse}},
)
def get_satellite_evidence() -> SatelliteEvidence:
    return evidence_reports.get_satellite_evidence()


@router.get(
    "/evidence/climate-comparison",
    response_model=ClimateComparison,
    responses={404: {"model": ErrorResponse}},
)
def get_climate_comparison() -> ClimateComparison:
    return evidence_reports.get_climate_comparison()
