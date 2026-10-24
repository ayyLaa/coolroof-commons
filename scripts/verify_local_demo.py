"""Exercises the local demo only; kept separate from fixture-based unit tests."""

import json
import os
import math
import struct
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

BACKEND_URL = "http://localhost:8000"
ORACLE_URL = "http://localhost:4020"
RPC_URL = "http://localhost:8545"
PAGE_SIZE = 200
EXPECTED_ROOF_COUNT = 726
DEPOSIT_WEI = 10**15
QUALITY_PERCENT = 60
RESERVE_PERCENT = 10
PERCENT_BASE = 100
IMAGE_SIZE = 400
ROOF_START = 100
ROOF_SIZE = 200
READING_COUNT = 16
THRESHOLDS = json.loads((Path(__file__).resolve().parents[1] / "schema/thresholds.json").read_text(encoding="utf-8"))
MIN_COVERAGE = THRESHOLDS["default"]["min_coverage_pct"]
MIN_DELTA = THRESHOLDS["by_city"]["athens"]["min_normalized_delta_c"]


def request_json(url: str, payload: dict | None = None) -> dict | list:
    content = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if payload is not None and os.getenv("WRITE_API_KEY"):
        headers["X-API-Key"] = os.environ["WRITE_API_KEY"]
    request = Request(url, data=content, headers=headers)
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def rpc(method: str, params: list) -> str | dict:
    reply = request_json(RPC_URL, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in reply:
        raise RuntimeError(str(reply["error"]))
    return reply["result"]


def verify_roof_count() -> None:
    roofs = []
    while True:
        page = request_json(f"{BACKEND_URL}/roofs?limit={PAGE_SIZE}&offset={len(roofs)}")
        roofs.extend(page)
        if len(page) < PAGE_SIZE:
            break
    assert len(roofs) == EXPECTED_ROOF_COUNT, f"Expected 726 roofs, got {len(roofs)}"
    assert sum(roof["data_source"] == "measured" for roof in roofs) == 723
    print("Snapshot: 726 roofs, 723 measured + 3 simulated")


def submit_scenario(roof_id: str, phase: str, expected: str, amount: int, health: dict) -> None:
    contractor = request_json(f"{BACKEND_URL}/contracts/{roof_id}")["contractor"]
    before = int(rpc("eth_getBalance", [contractor, "latest"]), 16)
    nonce = rpc("eth_getTransactionCount", [health["oracle_address"], "latest"])
    result = request_json(f"{ORACLE_URL}/submit", {"roof_id": roof_id, "phase": phase})
    assert result["status"] == expected, result
    after = int(rpc("eth_getBalance", [contractor, "latest"]), 16)
    assert after - before == amount, result
    if expected == "not_submitted":
        assert result["tx_hash"] is None, result
        assert rpc("eth_getTransactionCount", [health["oracle_address"], "latest"]) == nonce
    else:
        assert rpc("eth_getTransactionReceipt", [result["tx_hash"]])["status"] == "0x1"
    print(f"{roof_id}: {expected}, contractor received {amount} wei, tx={result['tx_hash']}")


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))


def coverage_photo(coverage_pct: float = 94.5) -> bytes:
    rows = bytearray()
    coated_width = round(ROOF_SIZE * coverage_pct / PERCENT_BASE)
    for y in range(IMAGE_SIZE):
        rows.append(0)
        for x in range(IMAGE_SIZE):
            on_roof = ROOF_START <= x < ROOF_START + ROOF_SIZE and ROOF_START <= y < ROOF_START + ROOF_SIZE
            color = (245, 245, 245) if x < ROOF_START + coated_width else (70, 70, 70)
            rows.extend(color if on_roof else (60, 140, 60))
    header = struct.pack("!2I5B", IMAGE_SIZE, IMAGE_SIZE, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(rows)) + png_chunk(b"IEND", b"")


def upload_photo(measurement_id: str, coverage_pct: float = 94.5) -> float:
    boundary = "coolroof-validation-boundary"
    prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="roof.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
    request = Request(f"{BACKEND_URL}/measurements/{measurement_id}/photo", method="POST",
                      data=prefix + coverage_photo(coverage_pct) + f"\r\n--{boundary}--\r\n".encode(),
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                               **({"X-API-Key": os.environ["WRITE_API_KEY"]} if os.getenv("WRITE_API_KEY") else {})})
    with urlopen(request, timeout=180) as response:
        return json.load(response)["coverage_pct"]


def verify_coverage_boundaries(health: dict) -> None:
    for index, coverage in enumerate((84.5, 85.0)):
        start = datetime.fromisoformat("2026-07-20T08:01:00+00:00") + timedelta(minutes=index)
        readings = [{"timestamp": (start + timedelta(minutes=minute)).isoformat(),
                     "surface_temp_c": round(46.1 + 2.3 * (1 - math.exp(-0.35 * minute)) + math.sin(minute + index) * 0.1, 2)}
                    for minute in range(READING_COUNT)]
        measurement = request_json(f"{BACKEND_URL}/measurements", {
            "roof_id": "ATH-0287", "phase": "after", "device_id": "VALIDATION-BOUNDARY",
            "data_source": "simulated", "readings": readings,
        })
        actual = upload_photo(measurement["measurement_id"], coverage)
        assert abs(actual - coverage) < 0.1, actual
        verification = request_json(f"{BACKEND_URL}/verification/ATH-0287")
        assert verification["normalized_delta_c"] <= MIN_DELTA, verification
        expected = "not_submitted" if coverage < MIN_COVERAGE else "released"
        amount = 0 if coverage < MIN_COVERAGE else DEPOSIT_WEI * QUALITY_PERCENT // PERCENT_BASE
        submit_scenario("ATH-0287", "quality", expected, amount, health)
        print(f"Coverage boundary {coverage}%: {expected}")


def verify_passing_but_flagged(health: dict) -> None:
    start = datetime.fromisoformat("2026-07-20T08:00:30+00:00")
    measurement = request_json(f"{BACKEND_URL}/measurements", {
        "roof_id": "ATH-0287", "phase": "after", "device_id": "VALIDATION-FROZEN",
        "data_source": "simulated", "readings": [
            {"timestamp": (start + timedelta(minutes=index)).isoformat(), "surface_temp_c": 40.0}
            for index in range(READING_COUNT)
        ],
    })
    upload_photo(measurement["measurement_id"])
    verification = request_json(f"{BACKEND_URL}/verification/ATH-0287")
    assert verification["status"] == "flagged", verification
    assert verification["normalized_delta_c"] <= MIN_DELTA, verification
    assert verification["coverage_pct"] >= MIN_COVERAGE, verification
    assert "repeated_value" in verification["anomaly_flags"], verification
    submit_scenario("ATH-0287", "quality", "not_submitted", 0, health)
    print("Passing cooling and coverage with a frozen-sensor flag: no transaction and no payment")


def main() -> None:
    health = request_json(f"{ORACLE_URL}/health")
    assert health["chain_id"] == 31337 and health["network"] == "local", "Local chain required"
    verify_roof_count()
    submit_scenario("ATH-0142", "quality", "released", DEPOSIT_WEI * QUALITY_PERCENT // PERCENT_BASE, health)
    submit_scenario("ATH-0287", "quality", "not_submitted", 0, health)
    submit_scenario("ATH-0355", "durability", "force_majeure", DEPOSIT_WEI * RESERVE_PERCENT // PERCENT_BASE, health)
    verify_passing_but_flagged(health)
    verify_coverage_boundaries(health)


if __name__ == "__main__":
    main()
