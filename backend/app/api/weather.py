from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.error import ErrorResponse
from app.schemas.weather import WeatherPoint
from app.services import weather as weather_service

router = APIRouter(tags=["weather"])


@router.get(
    "/weather/{roof_id}",
    response_model=list[WeatherPoint],
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_weather_history(
    roof_id: str, start: date, end: date, db: Session = Depends(get_db)
) -> list[WeatherPoint]:
    return weather_service.get_weather_history(db, roof_id, start, end)
