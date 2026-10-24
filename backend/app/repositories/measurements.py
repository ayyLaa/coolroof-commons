from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Measurement
from app.repositories.records import MeasurementData, measurement_data


def get_measurement(db: Session, measurement_id: UUID) -> Measurement | None:
    return db.get(Measurement, measurement_id)


def latest_measurement(db: Session, roof_id: str, phases: Sequence[str]) -> Measurement | None:
    query = (
        select(Measurement)
        .where(Measurement.roof_id == roof_id, Measurement.phase.in_(phases))
        .order_by(Measurement.measured_at.desc())
        .limit(1)
    )
    return db.scalars(query).first()


def latest_data(db: Session, roof_id: str, phases: Sequence[str]) -> MeasurementData | None:
    row = latest_measurement(db, roof_id, phases)
    return None if row is None else measurement_data(row)


def update_analysis(db: Session, measurement: MeasurementData, flags: list[str]) -> None:
    row = get_measurement(db, measurement.id)
    if row is not None:
        row.normalized_delta_c = measurement.normalized_delta_c
        row.coverage_pct = measurement.coverage_pct
        row.anomaly_flags = flags


def list_for_roof(db: Session, roof_id: str) -> list[Measurement]:
    query = (
        select(Measurement).where(Measurement.roof_id == roof_id).order_by(Measurement.measured_at)
    )
    return list(db.scalars(query))


def list_other_device_uploads(
    db: Session, device_id: str, exclude_id: UUID | None
) -> list[Measurement]:
    query = select(Measurement).where(Measurement.device_id == device_id)
    if exclude_id is not None:
        query = query.where(Measurement.id != exclude_id)
    return list(db.scalars(query))


def add_measurement(db: Session, measurement: Measurement) -> Measurement:
    db.add(measurement)
    db.flush()
    return measurement
