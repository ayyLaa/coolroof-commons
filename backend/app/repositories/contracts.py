from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContractEvent, ContractState


def list_tranches(db: Session, roof_id: str) -> list[ContractState]:
    query = (
        select(ContractState)
        .where(ContractState.roof_id == roof_id)
        .order_by(ContractState.released_at.is_(None), ContractState.released_at)
    )
    return list(db.scalars(query))


def get_tranche(db: Session, roof_id: str, tranche_name: str) -> ContractState | None:
    return db.get(ContractState, (roof_id, tranche_name))


def add_tranche(db: Session, state: ContractState) -> ContractState:
    db.add(state)
    db.flush()
    return state


def list_events(db: Session, roof_id: str) -> list[ContractEvent]:
    query = (
        select(ContractEvent)
        .where(ContractEvent.roof_id == roof_id)
        .order_by(ContractEvent.occurred_at, ContractEvent.block_number)
    )
    return list(db.scalars(query))


def find_event(
    db: Session, roof_id: str, tx_hash: str, event_name: str, tranche: str | None
) -> ContractEvent | None:
    query = select(ContractEvent).where(
        ContractEvent.roof_id == roof_id,
        ContractEvent.tx_hash == tx_hash,
        ContractEvent.event_name == event_name,
        ContractEvent.tranche.is_(None) if tranche is None else ContractEvent.tranche == tranche,
    )
    return db.scalars(query).first()


def add_event(db: Session, event: ContractEvent) -> ContractEvent:
    db.add(event)
    db.flush()
    return event
