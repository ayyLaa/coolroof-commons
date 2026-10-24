from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.api.security import require_operator
from app.schemas.demo import DemoResetResponse, DemoRoundStatus
from app.services import demo as demo_service

router = APIRouter(tags=["demo"])


@router.post("/demo/reset", response_model=DemoResetResponse, dependencies=[Depends(require_operator)])
def reset_demo(db: Session = Depends(get_db)) -> DemoResetResponse:
    return demo_service.start_round(db)


@router.get("/demo/round", response_model=DemoRoundStatus)
def get_demo_round(db: Session = Depends(get_db)) -> DemoRoundStatus:
    return demo_service.get_round(db)
