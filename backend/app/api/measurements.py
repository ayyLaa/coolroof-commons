from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.api.security import require_operator
from app.schemas.error import ErrorResponse
from app.schemas.measurement import (
    MeasurementCreateRequest,
    MeasurementCreateResponse,
    PhotoUploadResponse,
)
from app.services import measurements as measurement_service

router = APIRouter(tags=["measurements"])


@router.post(
    "/measurements",
    dependencies=[Depends(require_operator)],
    response_model=MeasurementCreateResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_measurement(
    payload: MeasurementCreateRequest, db: Session = Depends(get_db)
) -> MeasurementCreateResponse:
    return measurement_service.create_measurement(db, payload)


@router.post(
    "/measurements/{measurement_id}/photo",
    dependencies=[Depends(require_operator)],
    response_model=PhotoUploadResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def upload_measurement_photo(
    measurement_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> PhotoUploadResponse:
    content = file.file.read()
    return measurement_service.upload_photo(db, measurement_id, file.filename or "", content)
