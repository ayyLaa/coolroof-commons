from dataclasses import asdict
from app.infrastructure.chain_events import verify_event

from app.repositories.transactions import RepositoryContext, commit

from app.core.config import (
    CONTRACT_ADDRESS,
    CONTRACT_CONTRACTOR,
    CONTRACT_DEPOSIT_WEI,
    CONTRACT_SPONSOR,
    thresholds_for,
)
from app.core.exceptions import RoofNotFoundError, StaleRoundError
from app.models import ContractEvent, ContractState
from app.repositories import contracts as contract_repo
from app.repositories import demo as demo_repo
from app.repositories import roofs as roof_repo
from app.schemas.contract import (
    ContractEventCreate,
    ContractEventName,
    ContractEventRecord,
    ContractStatus,
    ContractThresholds,
    Tranche,
    TrancheName,
    TrancheStatus,
)

PERCENT_BASE = 100
# CoolRoofEscrow.sol QUALITY_PERCENT, DURABILITY_PERCENT and RESERVE_PERCENT.
TRANCHE_PERCENTS = {
    TrancheName.QUALITY: 60,
    TrancheName.DURABILITY: 30,
    TrancheName.FORCE_MAJEURE_RESERVE: 10,
}
# ForceMajeureApplied is absent: the escrow emits its own PaymentHeld and TrancheReleased
# alongside it, and those carry the state changes. UnreleasedReclaimed is absent too: the
# unpaid tranches go back to the sponsor without being released, so they keep their state.
STATUS_AFTER_EVENT = {
    ContractEventName.TRANCHE_RELEASED: TrancheStatus.RELEASED,
    ContractEventName.PAYMENT_HELD: TrancheStatus.HELD,
}


def tranche_amounts_wei(total_wei: int) -> dict[TrancheName, int]:
    """Same split as CoolRoofEscrow._releaseTranche: rounding dust goes to the reserve,
    so the amounts shown always add up to the deposit, as they do on chain."""
    quality = total_wei * TRANCHE_PERCENTS[TrancheName.QUALITY] // PERCENT_BASE
    durability = total_wei * TRANCHE_PERCENTS[TrancheName.DURABILITY] // PERCENT_BASE
    return {
        TrancheName.QUALITY: quality,
        TrancheName.DURABILITY: durability,
        TrancheName.FORCE_MAJEURE_RESERVE: total_wei - quality - durability,
    }


def to_tranche(state: ContractState, amounts: dict[TrancheName, int]) -> Tranche:
    name = TrancheName(state.tranche_name)
    amount = amounts.get(name)
    return Tranche(
        name=name,
        pct=state.pct,
        amount_wei=None if amount is None else str(amount),
        status=TrancheStatus(state.status),
        tx_hash=state.tx_hash,
        released_at=state.released_at,
    )


def to_event_record(event: ContractEvent) -> ContractEventRecord:
    return ContractEventRecord(
        roof_id=event.roof_id,
        event_name=ContractEventName(event.event_name),
        tranche=None if event.tranche is None else TrancheName(event.tranche),
        amount_wei=event.amount_wei,
        tx_hash=event.tx_hash,
        block_number=event.block_number,
        reason=event.reason,
        occurred_at=event.occurred_at,
        round=event.round,
    )


def get_contract_status(db: RepositoryContext, roof_id: str) -> ContractStatus:
    """Escrow terms are reported only for roofs that have tranches: a roof without a
    project on chain must not appear funded by the deployment's sponsor."""
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    states = contract_repo.list_tranches(db, roof_id)
    total_wei = CONTRACT_DEPOSIT_WEI if states else None
    amounts = {} if total_wei is None else tranche_amounts_wei(total_wei)
    return ContractStatus(
        roof_id=roof_id,
        contract_address=CONTRACT_ADDRESS if states else None,
        sponsor=CONTRACT_SPONSOR if states else None,
        contractor=CONTRACT_CONTRACTOR if states else None,
        total_amount_wei=None if total_wei is None else str(total_wei),
        thresholds=ContractThresholds(**asdict(thresholds_for(located.roof.city))),
        tranches=[to_tranche(state, amounts) for state in states],
        events=[to_event_record(event) for event in contract_repo.list_events(db, roof_id)],
    )


def _apply_to_tranche(db: RepositoryContext, roof_id: str, event: ContractEventCreate) -> None:
    status = STATUS_AFTER_EVENT.get(event.event_name)
    if status is None or event.tranche is None:
        return
    state = contract_repo.get_tranche(db, roof_id, event.tranche.value)
    if state is None:
        state = contract_repo.add_tranche(
            db,
            ContractState(
                roof_id=roof_id,
                tranche_name=event.tranche.value,
                pct=TRANCHE_PERCENTS[event.tranche],
                status=status.value,
            ),
        )
    state.status = status.value
    if status is TrancheStatus.RELEASED:
        state.tx_hash = event.tx_hash
        state.released_at = event.occurred_at


def record_event(db: RepositoryContext, roof_id: str, event: ContractEventCreate) -> ContractEventRecord:
    """Idempotent: the oracle replays events after a restart, and a replay must not
    duplicate the timeline."""
    if roof_repo.get_roof(db, roof_id) is None:
        raise RoofNotFoundError(roof_id)
    current = demo_repo.current_round(db)
    if event.round != current:
        raise StaleRoundError(event.round, current)
    verify_event(roof_id, event)
    tranche = None if event.tranche is None else event.tranche.value
    stored = contract_repo.find_event(db, roof_id, event.tx_hash, event.event_name.value, tranche)
    if stored is None:
        fields = event.model_dump(exclude={"event_name", "tranche"})
        stored = contract_repo.add_event(
            db,
            ContractEvent(
                roof_id=roof_id, event_name=event.event_name.value, tranche=tranche, **fields
            ),
        )
        _apply_to_tranche(db, roof_id, event)
        commit(db)
    return to_event_record(stored)
