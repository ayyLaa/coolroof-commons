from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.error import ErrorResponse
from app.schemas.verification import VerificationResult
from app.services import verification as verification_service

router = APIRouter(tags=["verification"])


@router.get(
    "/verification/{roof_id}",
    response_model=VerificationResult,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_verification(roof_id: str, db: Session = Depends(get_db)) -> VerificationResult:
    return verification_service.verify_roof(db, roof_id)
