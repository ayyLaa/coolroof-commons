from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Verification
from app.repositories import measurements
from app.repositories.records import MeasurementData
from app.schemas.verification import VerificationResult


def get_by_evidence_hash(db: Session, roof_id: str, evidence_hash: str) -> Verification | None:
    query = select(Verification).where(
        Verification.roof_id == roof_id, Verification.evidence_hash == evidence_hash
    )
    return db.scalars(query).first()


def add_verification(db: Session, verification: Verification) -> Verification:
    db.add(verification)
    db.flush()
    return verification


def save_result(db: Session, result: VerificationResult, after: MeasurementData, flags: list[str]) -> None:
    after.normalized_delta_c = result.normalized_delta_c
    measurements.update_analysis(db, after, flags)
    if get_by_evidence_hash(db, result.roof_id, result.evidence_hash) is None:
        add_verification(db, Verification(
            roof_id=result.roof_id, status=result.status, payload=result.model_dump(mode="json"),
            evidence_hash=result.evidence_hash, device_signature=result.device_signature,
        ))
    db.commit()
