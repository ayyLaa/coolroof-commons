from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.error import ErrorResponse
from app.schemas.roof import RoofDetail, RoofSummary
from app.schemas.series import SimulatedSeriesResponse
from app.services import roofs as roof_service
from app.services import series as series_service

router = APIRouter(tags=["roofs"])


@router.get("/roofs", response_model=list[RoofSummary])
def list_roofs(
    city: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    min_score: float | None = None,
    include_geometry: bool = False,
    db: Session = Depends(get_db),
) -> list[RoofSummary]:
    return roof_service.list_roofs(
        db,
        city=city,
        page=(limit, offset),
        min_score=min_score,
        include_geometry=include_geometry,
    )


@router.get(
    "/roofs/{roof_id}",
    response_model=RoofDetail,
    responses={404: {"model": ErrorResponse}},
)
def get_roof(roof_id: str, db: Session = Depends(get_db)) -> RoofDetail:
    return roof_service.get_roof_detail(db, roof_id)


@router.get(
    "/roofs/{roof_id}/series",
    response_model=SimulatedSeriesResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_simulated_series(
    roof_id: str,
    before: date = series_service.DEFAULT_BEFORE_DAY,
    after: date = series_service.DEFAULT_AFTER_DAY,
    db: Session = Depends(get_db),
) -> SimulatedSeriesResponse:
    return series_service.get_simulated_series(db, roof_id, before, after)
