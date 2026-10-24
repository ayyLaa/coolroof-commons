"""Backend signatures preserve evidence provenance within the prototype's trust model.
Real device authentication requires a separate device registry and signing protocol."""

import binascii
import hashlib
import json

from eth_account import Account
from eth_account.messages import encode_defunct

from app.core.config import DEVICE_PRIVATE_KEY
from app.core.exceptions import SigningUnavailableError

HEX_PREFIX = "0x"


def canonical_json(payload: object) -> bytes:
    """Sorted keys and fixed separators: the same evidence must always hash the same."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def compute_evidence_hash(measurements: list[dict], photo_bytes: bytes, weather: list[dict]) -> str:
    """Each part is hashed separately and the digests are hashed together; plain
    concatenation would let bytes shift between parts and still give the same hash."""
    parts = (canonical_json(measurements), photo_bytes, canonical_json(weather))
    combined = b"".join(hashlib.sha256(part).digest() for part in parts)
    return HEX_PREFIX + hashlib.sha256(combined).hexdigest()


def sign_evidence(evidence_hash: str, private_key: str | None = None) -> str:
    """EIP-191 personal_sign, so a contract can recover the signer with
    ECDSA.recover(toEthSignedMessageHash(evidenceHash), signature)."""
    private_key = DEVICE_PRIVATE_KEY if private_key is None else private_key
    if not private_key:
        raise SigningUnavailableError("DEVICE_PRIVATE_KEY is not set; see backend/.env.example.")
    try:
        signed = Account.sign_message(encode_defunct(hexstr=evidence_hash), private_key)
    except (ValueError, binascii.Error) as error:
        raise SigningUnavailableError("DEVICE_PRIVATE_KEY is not a valid private key.") from error
    return HEX_PREFIX + bytes(signed.signature).hex()
