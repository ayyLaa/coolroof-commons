from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.api.security import require_oracle
from app.schemas.contract import ContractEventCreate, ContractEventRecord, ContractStatus
from app.schemas.error import ErrorResponse
from app.services import contracts as contract_service

router = APIRouter(tags=["contracts"])


@router.get(
    "/contracts/{roof_id}",
    response_model=ContractStatus,
    responses={404: {"model": ErrorResponse}},
)
def get_contract_status(roof_id: str, db: Session = Depends(get_db)) -> ContractStatus:
    return contract_service.get_contract_status(db, roof_id)


@router.post(
    "/contracts/{roof_id}/events",
    dependencies=[Depends(require_oracle)],
    response_model=ContractEventRecord,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def record_contract_event(
    roof_id: str, event: ContractEventCreate, db: Session = Depends(get_db)
) -> ContractEventRecord:
    return contract_service.record_event(db, roof_id, event)
