from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    SIMULATED,
    ContractEvent,
    ContractState,
    DemoRound,
    Measurement,
    Roof,
    Verification,
    WeatherRecord,
)

# Children before parents, so foreign keys never block a delete. Contract events and
# tranche states are absent: they mirror the chain, and only a new round leaves it behind.
ROOF_OWNED_TABLES = (Verification, Measurement)
CHAIN_MIRROR_TABLES = (ContractEvent, ContractState)
ORIGINAL_ROUND = 0


def current_round(db: Session) -> int:
    """No round started yet means the unsuffixed original projects."""
    return db.scalar(select(func.max(DemoRound.round))) or ORIGINAL_ROUND


def add_round(db: Session, round_number: int) -> None:
    db.add(DemoRound(round=round_number))
    db.flush()


def delete_chain_mirror(db: Session, roof_ids: Sequence[str]) -> dict[str, int]:
    return {
        model.__tablename__: db.execute(delete(model).where(model.roof_id.in_(roof_ids))).rowcount
        for model in CHAIN_MIRROR_TABLES
    }


def list_measurement_ids(db: Session, roof_ids: Sequence[str]) -> list[UUID]:
    return list(db.scalars(select(Measurement.id).where(Measurement.roof_id.in_(roof_ids))))


def delete_demo_rows(db: Session, roof_ids: Sequence[str]) -> dict[str, int]:
    """Roofs themselves stay: real Open-Meteo weather and the chain's events reference them."""
    counts = {
        model.__tablename__: db.execute(
            delete(model).where(model.roof_id.in_(roof_ids))
        ).rowcount
        for model in ROOF_OWNED_TABLES
    }
    # Only the seed's own fabricated weather goes; third_party rows survive a reset.
    counts[WeatherRecord.__tablename__] = db.execute(
        delete(WeatherRecord).where(
            WeatherRecord.roof_id.in_(roof_ids), WeatherRecord.data_source == SIMULATED
        )
    ).rowcount
    return counts


def write_demo_rows(
    db: Session,
    roofs: Sequence[Roof],
    rows: Sequence[Measurement | Verification | WeatherRecord],
) -> None:
    for roof in roofs:
        db.merge(roof)
    # Roofs are flushed first so the rows referencing them can be inserted.
    db.flush()
    db.add_all(rows)
    db.flush()


def add_missing_tranches(db: Session, states: Sequence[ContractState]) -> int:
    """A tranche the chain has already moved keeps its relayed state."""
    missing = [
        state
        for state in states
        if db.get(ContractState, (state.roof_id, state.tranche_name)) is None
    ]
    db.add_all(missing)
    db.flush()
    return len(missing)
