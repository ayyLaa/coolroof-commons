import os

import httpx
from eth_abi import decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

from app.core.exceptions import InvalidChainEventError, SecurityConfigurationError
from app.schemas.contract import ContractEventCreate

RPC_TIMEOUT_SECONDS = 10
DECIMAL_SCALE = 10
TRANCHES = ("QUALITY", "DURABILITY", "FORCE_MAJEURE_RESERVE")
EVENTS = {
    "TrancheReleased": ("TrancheReleased(string,uint8,uint256,address)", ("string", "uint8", "uint256")),
    "PaymentHeld": ("PaymentHeld(string,uint8,string)", ("string", "uint8", "string")),
    "ForceMajeureApplied": ("ForceMajeureApplied(string,uint256,uint256)", ("string", "uint256", "uint256")),
    "UnreleasedReclaimed": ("UnreleasedReclaimed(string,address,uint256)", ("string", "uint256")),
}


def _rpc(url: str, method: str, params: list) -> object:
    try:
        response = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=RPC_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise ValueError("RPC rejected request")
        return payload["result"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise SecurityConfigurationError("Cannot independently verify the chain event.") from error


def _event_fields(name: str, values: tuple) -> dict:
    if name == "TrancheReleased":
        return {"tranche": TRANCHES[values[1]], "amount_wei": str(values[2]), "reason": None}
    if name == "PaymentHeld":
        return {"tranche": TRANCHES[values[1]], "amount_wei": None, "reason": values[2]}
    if name == "ForceMajeureApplied":
        return {"tranche": None, "amount_wei": None,
                "reason": f"gusts {values[1] / DECIMAL_SCALE:.1f} m/s, {values[2] / DECIMAL_SCALE:.1f} mm precipitation"}
    return {"tranche": None, "amount_wei": str(values[1]), "reason": None}


def _matching_log(log: dict, address: str, roof_id: str, event: ContractEventCreate) -> bool:
    signature, types = EVENTS[event.event_name.value]
    topic = "0x" + keccak(text=signature).hex()
    if log.get("address", "").lower() != address.lower() or log.get("topics", [None])[0] != topic:
        return False
    try:
        values = decode(types, bytes.fromhex(log["data"].removeprefix("0x")))
        chain_roof = f"{roof_id}#{event.round}" if event.round else roof_id
        fields = event.model_dump(mode="json")
        return values[0] == chain_roof and all(fields[key] == value for key, value in _event_fields(event.event_name.value, values).items())
    except (ValueError, KeyError, IndexError, TypeError, DecodingError):
        return False


def _check_receipt(url: str, address: str, roof_id: str, event: ContractEventCreate) -> None:
    receipt = _rpc(url, "eth_getTransactionReceipt", [event.tx_hash])
    if not isinstance(receipt, dict) or receipt.get("status") != "0x1" or receipt.get("transactionHash", "").lower() != event.tx_hash.lower():
        raise InvalidChainEventError("No successful transaction receipt matches this event.")
    if int(receipt["blockNumber"], 16) != event.block_number:
        raise InvalidChainEventError("The event block does not match its transaction receipt.")
    block = _rpc(url, "eth_getBlockByNumber", [receipt["blockNumber"], False])
    if not isinstance(block, dict) or block.get("hash") != receipt.get("blockHash"):
        raise InvalidChainEventError("The event is not on the current canonical chain.")
    if int(block["timestamp"], 16) != int(event.occurred_at.timestamp()):
        raise InvalidChainEventError("The event timestamp does not match its block.")
    if not any(_matching_log(log, address, roof_id, event) for log in receipt.get("logs", [])):
        raise InvalidChainEventError("No matching event log was emitted by the configured escrow.")


def verify_event(roof_id: str, event: ContractEventCreate) -> None:
    url = os.getenv("EVENT_RPC_URL", "")
    if not url and os.getenv("APP_MODE", "local") == "local":
        return
    address = os.getenv("CONTRACT_ADDRESS", "")
    if not url or not address:
        raise SecurityConfigurationError("EVENT_RPC_URL and CONTRACT_ADDRESS are required to verify events.")
    try:
        chain_id = _rpc(url, "eth_chainId", [])
        if int(chain_id, 16) != int(os.getenv("EXPECTED_CHAIN_ID", "31337")):
            raise InvalidChainEventError("The event RPC is connected to the wrong chain.")
        _check_receipt(url, address, roof_id, event)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise InvalidChainEventError("The RPC returned an invalid event receipt.") from error
