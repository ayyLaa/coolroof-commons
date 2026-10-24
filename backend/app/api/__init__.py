from fastapi import APIRouter

from app.api import contracts, demo, evidence, measurements, roofs, verification, weather

router = APIRouter()
router.include_router(roofs.router)
router.include_router(measurements.router)
router.include_router(verification.router)
router.include_router(weather.router)
router.include_router(contracts.router)
router.include_router(evidence.router)
router.include_router(demo.router)

__all__ = ["router"]
