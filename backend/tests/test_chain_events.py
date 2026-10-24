from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from eth_abi import encode
from eth_utils import keccak

from app.core.exceptions import InvalidChainEventError, SecurityConfigurationError
from app.infrastructure import chain_events
from app.schemas.contract import ContractEventCreate

ADDRESS = "0x" + "11" * 20
TX = "0x" + "ab" * 32
EVENT = ContractEventCreate(event_name="TrancheReleased", tranche="QUALITY", amount_wei="600",
                            tx_hash=TX, block_number=42, occurred_at=datetime(2026, 7, 15, tzinfo=UTC), round=2)


def receipt() -> dict:
    return {"transactionHash": TX, "status": "0x1", "blockNumber": "0x2a", "blockHash": "canonical",
            "logs": [{"address": ADDRESS, "topics": ["0x" + keccak(text=chain_events.EVENTS["TrancheReleased"][0]).hex()],
                      "data": "0x" + encode(["string", "uint8", "uint256"], ["ATH-0142#2", 0, 600]).hex()}]}


def wire(monkeypatch: pytest.MonkeyPatch, value: dict) -> None:
    monkeypatch.setenv("EVENT_RPC_URL", "http://fixture")
    monkeypatch.setenv("CONTRACT_ADDRESS", ADDRESS)
    monkeypatch.setenv("EXPECTED_CHAIN_ID", "31337")
    block = {"hash": "canonical", "timestamp": hex(int(EVENT.occurred_at.timestamp()))}
    monkeypatch.setattr(chain_events, "_rpc", MagicMock(side_effect=["0x7a69", value, block]))


def test_receipt_and_decoded_fields_are_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch, receipt())
    chain_events.verify_event("ATH-0142", EVENT)


@pytest.mark.parametrize("change", ["amount", "contract", "block", "revert", "fork"])
def test_fabricated_event_is_rejected(change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    value = receipt()
    if change == "contract": value["logs"][0]["address"] = "0x" + "22" * 20
    if change == "block": value["blockNumber"] = "0x2b"
    if change == "revert": value["status"] = "0x0"
    if change == "fork": value["blockHash"] = "orphan"
    wire(monkeypatch, value)
    event = EVENT.model_copy(update={"amount_wei": "999"}) if change == "amount" else EVENT
    with pytest.raises(InvalidChainEventError):
        chain_events.verify_event("ATH-0142", event)


def test_remote_mode_requires_rpc_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.delenv("EVENT_RPC_URL", raising=False)
    with pytest.raises(SecurityConfigurationError):
        chain_events.verify_event("ATH-0142", EVENT)
