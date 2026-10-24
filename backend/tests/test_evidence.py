import re

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from app.core.exceptions import SigningUnavailableError
from app.schemas.verification import DEVICE_SIGNATURE_PATTERN, EVIDENCE_HASH_PATTERN
from app.services.evidence import compute_evidence_hash, sign_evidence
from tests.conftest import TEST_PRIVATE_KEY

MEASUREMENTS = [{"measurement_id": "m1", "raw_readings": [{"surface_temp_c": 48.6}]}]
WEATHER = [{"timestamp": "2026-07-15T10:00:00Z", "max_gust_ms": 6.0}]


def test_hash_is_deterministic_and_prefixed() -> None:
    first = compute_evidence_hash(MEASUREMENTS, b"photo", WEATHER)

    assert first == compute_evidence_hash(MEASUREMENTS, b"photo", WEATHER)
    assert re.fullmatch(EVIDENCE_HASH_PATTERN, first)


@pytest.mark.parametrize(
    "changed",
    [
        ([{"measurement_id": "m1", "raw_readings": [{"surface_temp_c": 48.7}]}], b"photo", WEATHER),
        (MEASUREMENTS, b"photo2", WEATHER),
        (MEASUREMENTS, b"photo", [{"timestamp": "2026-07-15T10:00:00Z", "max_gust_ms": 6.1}]),
    ],
)
def test_any_tampering_changes_the_hash(changed: tuple) -> None:
    assert compute_evidence_hash(*changed) != compute_evidence_hash(MEASUREMENTS, b"photo", WEATHER)


def test_signature_recovers_device_address() -> None:
    evidence_hash = compute_evidence_hash(MEASUREMENTS, b"photo", WEATHER)

    signature = sign_evidence(evidence_hash, TEST_PRIVATE_KEY)

    assert re.fullmatch(DEVICE_SIGNATURE_PATTERN, signature)
    recovered = Account.recover_message(encode_defunct(hexstr=evidence_hash), signature=signature)
    assert recovered == Account.from_key(TEST_PRIVATE_KEY).address


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.evidence.DEVICE_PRIVATE_KEY", "")

    with pytest.raises(SigningUnavailableError):
        sign_evidence("0x" + "00" * 32)


def test_invalid_key_raises() -> None:
    with pytest.raises(SigningUnavailableError):
        sign_evidence("0x" + "00" * 32, "0xnot-a-key")
