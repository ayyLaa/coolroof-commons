from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import RoofNotFoundError, StaleRoundError
from app.models import ContractEvent, ContractState
from app.repositories.roofs import RoofWithLocation
from app.schemas.contract import ContractEventCreate, TrancheName
from app.services import contracts

SPONSOR = "0x" + "aa" * 20
TX_HASH = "0x" + "ab" * 32
RELEASED_AT = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
CURRENT_ROUND = 0


def release_event(**overrides: object) -> ContractEventCreate:
    values = {
        "event_name": "TrancheReleased",
        "tranche": "QUALITY",
        "amount_wei": "600000000000000000",
        "tx_hash": TX_HASH,
        "block_number": 42,
        "occurred_at": RELEASED_AT,
    }
    return ContractEventCreate(**{**values, **overrides})


@pytest.fixture
def tranches() -> dict[str, ContractState]:
    return {
        name.value: ContractState(
            roof_id="ATH-0142", tranche_name=name.value, pct=pct, status="pending"
        )
        for name, pct in contracts.TRANCHE_PERCENTS.items()
    }


@pytest.fixture
def stored_events() -> list[ContractEvent]:
    return []


@pytest.fixture
def wired(
    monkeypatch: pytest.MonkeyPatch,
    roof: RoofWithLocation,
    tranches: dict[str, ContractState],
    stored_events: list[ContractEvent],
) -> None:
    monkeypatch.setattr("app.repositories.roofs.get_roof", lambda _db, _rid: roof)
    monkeypatch.setattr(
        "app.repositories.contracts.list_tranches", lambda _db, _rid: list(tranches.values())
    )
    monkeypatch.setattr(
        "app.repositories.contracts.get_tranche", lambda _db, _rid, name: tranches.get(name)
    )
    monkeypatch.setattr("app.repositories.contracts.list_events", lambda _db, _rid: stored_events)
    def find_event(_db: object, _rid: str, *key: str | None) -> ContractEvent | None:
        return next((e for e in stored_events if (e.tx_hash, e.event_name, e.tranche) == key), None)

    monkeypatch.setattr("app.repositories.contracts.find_event", find_event)
    monkeypatch.setattr(
        "app.repositories.contracts.add_event", lambda _db, e: stored_events.append(e) or e
    )
    monkeypatch.setattr(contracts, "CONTRACT_SPONSOR", SPONSOR)
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: CURRENT_ROUND)


def test_tranche_amounts_follow_the_escrow_and_sum_to_the_deposit() -> None:
    amounts = contracts.tranche_amounts_wei(10**18 + 7)

    assert amounts[TrancheName.QUALITY] == 6 * 10**17 + 4
    assert amounts[TrancheName.DURABILITY] == 3 * 10**17 + 2
    assert sum(amounts.values()) == 10**18 + 7


def test_status_reports_terms_amounts_and_city_thresholds(
    wired: None, roof: RoofWithLocation
) -> None:
    roof.roof.city = "London"

    status = contracts.get_contract_status(MagicMock(), "ATH-0142")

    assert status.sponsor == SPONSOR
    assert status.total_amount_wei == str(contracts.CONTRACT_DEPOSIT_WEI)
    assert status.thresholds.min_normalized_delta_c == -6.0
    assert [t.name for t in status.tranches] == list(contracts.TRANCHE_PERCENTS)
    assert sum(int(t.amount_wei) for t in status.tranches) == contracts.CONTRACT_DEPOSIT_WEI


def test_roof_without_tranches_has_no_contract_terms(
    wired: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.repositories.contracts.list_tranches", lambda _db, _rid: [])

    status = contracts.get_contract_status(MagicMock(), "ATH-0142")

    assert (status.sponsor, status.total_amount_wei, status.tranches) == (None, None, [])


def test_release_event_is_recorded_and_releases_the_tranche(
    wired: None, tranches: dict[str, ContractState], stored_events: list[ContractEvent]
) -> None:
    db = MagicMock()

    record = contracts.record_event(db, "ATH-0142", release_event())

    quality = tranches["QUALITY"]
    assert (quality.status, quality.tx_hash, quality.released_at) == (
        "released",
        TX_HASH,
        RELEASED_AT,
    )
    assert record.event_name.value == "TrancheReleased"
    assert len(stored_events) == 1
    db.commit.assert_called_once()


def test_replayed_event_is_not_recorded_twice(
    wired: None, stored_events: list[ContractEvent]
) -> None:
    contracts.record_event(MagicMock(), "ATH-0142", release_event())
    contracts.record_event(MagicMock(), "ATH-0142", release_event())

    assert len(stored_events) == 1


def test_force_majeure_event_changes_no_tranche(
    wired: None, tranches: dict[str, ContractState]
) -> None:
    event = release_event(event_name="ForceMajeureApplied", tranche=None, amount_wei=None)

    contracts.record_event(MagicMock(), "ATH-0142", event)

    assert {state.status for state in tranches.values()} == {"pending"}


def test_reclaim_event_is_recorded_without_a_tranche(
    wired: None, tranches: dict[str, ContractState], stored_events: list[ContractEvent]
) -> None:
    event = release_event(event_name="UnreleasedReclaimed", tranche=None, amount_wei="400")

    record = contracts.record_event(MagicMock(), "ATH-0142", event)

    assert (record.event_name.value, record.amount_wei) == ("UnreleasedReclaimed", "400")
    assert len(stored_events) == 1
    assert {state.status for state in tranches.values()} == {"pending"}


@pytest.mark.parametrize("round_number", [1, 3])
def test_event_from_another_round_is_rejected(
    wired: None,
    monkeypatch: pytest.MonkeyPatch,
    tranches: dict[str, ContractState],
    stored_events: list[ContractEvent],
    round_number: int,
) -> None:
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: 2)

    with pytest.raises(StaleRoundError, match="round 2"):
        contracts.record_event(MagicMock(), "ATH-0142", release_event(round=round_number))

    assert stored_events == []
    assert tranches["QUALITY"].status == "pending"


def test_event_of_the_current_round_is_recorded_with_it(
    wired: None, monkeypatch: pytest.MonkeyPatch, stored_events: list[ContractEvent]
) -> None:
    monkeypatch.setattr("app.repositories.demo.current_round", lambda _db: 2)

    record = contracts.record_event(MagicMock(), "ATH-0142", release_event(round=2))

    assert record.round == 2
    assert stored_events[0].round == 2


def test_event_for_unknown_roof_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.repositories.roofs.get_roof", lambda _db, _rid: None)

    with pytest.raises(RoofNotFoundError):
        contracts.record_event(MagicMock(), "ATH-9999", release_event())


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_name": "PaymentHeld", "tranche": None},
        {"event_name": "UnreleasedReclaimed", "tranche": None, "amount_wei": None},
        {"amount_wei": None},
        {"amount_wei": "-1"},
        {"tx_hash": "0x1234"},
    ],
)
def test_incomplete_events_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        release_event(**overrides)
