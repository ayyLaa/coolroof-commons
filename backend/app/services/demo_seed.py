"""The three demo roofs, built as unsaved ORM rows.

Building is kept apart from writing (services/demo.py) so scripts/metrics.py can score
the scenarios without a database, and POST /demo/reset and scripts/seed.py restore
exactly the same rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import NAMESPACE_DNS, UUID, uuid5

from geoalchemy2.elements import WKTElement

from app.core.config import thresholds_for
from app.core.timezones import timezone_for, to_utc
from app.models import SIMULATED, ContractState, Measurement, Roof, Verification, WeatherRecord
from app.schemas.contract import TrancheName, TrancheStatus
from app.schemas.verification import VerificationResult
from app.services.contracts import TRANCHE_PERCENTS

DEMO_CITY = "Athens"
THRESHOLDS = thresholds_for(DEMO_CITY)

METERS_PER_DEGREE_LATITUDE = 111_320.0
MEASUREMENT_WINDOW_MINUTES = 15
MEASUREMENT_STEP_MINUTES = 1
PLATEAU_SAMPLE_SIZE = 3
WARMUP_RATE = 0.35
SENSOR_NOISE_STD_C = 0.25
STORM_NOISE_STD_C = 2.5

Curve = list[tuple[int, float]]


@dataclass(frozen=True)
class WeatherValues:
    ambient_c: float
    radiation_wm2: float
    wind_ms: float
    max_gust_ms: float
    precipitation_mm: float = 0.0


@dataclass(frozen=True)
class StormCheck:
    """A durability recheck whose readings a storm has scrambled."""

    weather: WeatherValues
    center_c: float


@dataclass(frozen=True)
class DemoScenario:
    roof_id: str
    device_id: str
    lat: float
    lon: float
    area_m2: float
    albedo: float
    priority_score: float
    status: str
    # Local wall-clock times; stored as UTC like every other timestamp.
    before_local: datetime
    after_local: datetime
    # (start, plateau) of the warm-up curve, in Celsius.
    before_c: tuple[float, float]
    after_c: tuple[float, float]
    coverage_pct: float
    weather: WeatherValues
    storm: StormCheck | None = None


@dataclass
class DemoRoofRows:
    roof: Roof
    measurements: list[Measurement] = field(default_factory=list)
    verifications: list[Verification] = field(default_factory=list)
    weather_records: list[WeatherRecord] = field(default_factory=list)
    contract_states: list[ContractState] = field(default_factory=list)


SCENARIOS = (
    # A dark, hot roof cools well past the threshold.
    DemoScenario(
        roof_id="ATH-0142",
        device_id="DEV-0391",
        lat=37.9838,
        lon=23.7275,
        area_m2=850.0,
        albedo=0.12,
        priority_score=0.92,
        status="verified",
        before_local=datetime(2026, 6, 1, 10, 0),
        after_local=datetime(2026, 7, 15, 11, 0),
        before_c=(58.3, 61.6),
        after_c=(46.3, 48.6),
        coverage_pct=94.5,
        weather=WeatherValues(ambient_c=34.0, radiation_wm2=850.0, wind_ms=3.0, max_gust_ms=6.0),
    ),
    # Normal weather, so the small drop is down to a poor coating.
    DemoScenario(
        roof_id="ATH-0287",
        device_id="DEV-0214",
        lat=37.9795,
        lon=23.7162,
        area_m2=540.0,
        albedo=0.13,
        priority_score=0.58,
        status="flagged",
        before_local=datetime(2026, 6, 5, 10, 0),
        after_local=datetime(2026, 7, 20, 11, 0),
        before_c=(59.0, 61.0),
        after_c=(57.0, 58.0),
        coverage_pct=61.0,
        weather=WeatherValues(ambient_c=31.0, radiation_wm2=800.0, wind_ms=3.0, max_gust_ms=6.0),
    ),
    # Verified, then a storm during the durability recheck triggers force majeure.
    DemoScenario(
        roof_id="ATH-0355",
        device_id="DEV-0502",
        lat=37.9686,
        lon=23.7295,
        area_m2=710.0,
        albedo=0.11,
        priority_score=0.81,
        status="durability_recheck_required",
        before_local=datetime(2026, 6, 10, 10, 0),
        after_local=datetime(2026, 7, 25, 11, 0),
        before_c=(57.2, 59.8),
        after_c=(45.8, 48.0),
        coverage_pct=90.0,
        weather=WeatherValues(ambient_c=32.0, radiation_wm2=820.0, wind_ms=3.0, max_gust_ms=6.0),
        storm=StormCheck(
            weather=WeatherValues(
                ambient_c=19.0,
                radiation_wm2=150.0,
                wind_ms=14.0,
                max_gust_ms=24.0,
                precipitation_mm=68.0,
            ),
            center_c=50.0,
        ),
    ),
)
DEMO_ROOF_IDS = tuple(scenario.roof_id for scenario in SCENARIOS)


def _square_polygon(lat: float, lon: float, area_m2: float) -> WKTElement:
    half_m = math.sqrt(area_m2) / 2
    meters_per_degree_lon = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(lat))
    dlat = half_m / METERS_PER_DEGREE_LATITUDE
    dlon = half_m / meters_per_degree_lon
    corners = [
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon + dlon, lat + dlat),
        (lon - dlon, lat + dlat),
        (lon - dlon, lat - dlat),
    ]
    wkt = "POLYGON((" + ", ".join(f"{x} {y}" for x, y in corners) + "))"
    return WKTElement(wkt, srid=4326)


def _minutes() -> range:
    return range(0, MEASUREMENT_WINDOW_MINUTES + 1, MEASUREMENT_STEP_MINUTES)


def _rising_plateau_curve(start_c: float, plateau_c: float, seed: str) -> Curve:
    """A physically plausible warm-up: the sensor approaches the roof's plateau."""
    rng = random.Random(seed)
    readings = []
    for t in _minutes():
        base = start_c + (plateau_c - start_c) * (1 - math.exp(-WARMUP_RATE * t))
        readings.append((t, round(base + rng.gauss(0, SENSOR_NOISE_STD_C), 2)))
    return readings


def _corrupted_curve(center_c: float, seed: str) -> Curve:
    """Readings scrambled by storm noise, with no plateau to measure."""
    rng = random.Random(seed)
    return [(t, round(center_c + rng.gauss(0, STORM_NOISE_STD_C), 2)) for t in _minutes()]


def _plateau_mean(curve: Curve) -> float:
    return sum(temp for _, temp in curve[-PLATEAU_SAMPLE_SIZE:]) / PLATEAU_SAMPLE_SIZE


def _to_raw_readings(curve: Curve, start_time: datetime) -> list[dict]:
    return [
        {
            "timestamp": (start_time + timedelta(minutes=t)).isoformat().replace("+00:00", "Z"),
            "surface_temp_c": temp,
        }
        for t, temp in curve
    ]


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _evidence_hash(payload: dict) -> str:
    return "0x" + _sha256_hex(json.dumps(payload, sort_keys=True))


def _device_signature(payload: dict, device_id: str) -> str:
    """Deterministic stand-in with the shape of a signature: the seed is simulated and
    has no device key to sign with."""
    canonical = json.dumps(payload, sort_keys=True)
    r = _sha256_hex(f"{device_id}:r:{canonical}")
    s = _sha256_hex(f"{device_id}:s:{canonical}")
    return f"0x{r}{s}1b"


def _force_majeure_flags(weather: WeatherValues) -> list[str]:
    flags = []
    if weather.max_gust_ms > THRESHOLDS.force_majeure_gust_ms:
        flags.append("extreme_wind_event")
    if weather.precipitation_mm > THRESHOLDS.force_majeure_precip_mm:
        flags.append("heavy_precipitation")
    return flags


def _quality_flags(delta_c: float, coverage_pct: float) -> list[str]:
    flags = []
    if delta_c > THRESHOLDS.min_normalized_delta_c:
        flags.append("normalized_delta_below_threshold")
    if coverage_pct < THRESHOLDS.min_coverage_pct:
        flags.append("coverage_below_threshold")
    return flags


def _decide(
    delta_c: float, coverage_pct: float, weather: WeatherValues
) -> tuple[str, bool, list[str]]:
    force_majeure_flags = _force_majeure_flags(weather)
    if force_majeure_flags:
        return "insufficient_data", True, force_majeure_flags
    quality_flags = _quality_flags(delta_c, coverage_pct)
    return ("flagged" if quality_flags else "approved"), False, quality_flags


def _quality_reason(delta_c: float, coverage_pct: float, flags: list[str]) -> str:
    threshold_c = THRESHOLDS.min_normalized_delta_c
    min_coverage = THRESHOLDS.min_coverage_pct
    if "normalized_delta_below_threshold" in flags:
        cooling = f"Surface temperature fell only {-delta_c:.1f} C, short of the"
    else:
        cooling = f"Surface temperature fell {-delta_c:.1f} C, past the"
    side = "below" if "coverage_below_threshold" in flags else "above"
    reason = (
        f"{cooling} {threshold_c:.1f} C threshold. Coating coverage is {coverage_pct:.1f}%, "
        f"{side} the {min_coverage:.0f}% threshold."
    )
    if flags:
        reason += " The weather was normal, so the shortfall points to the coating."
    return reason


def _force_majeure_reason(weather: WeatherValues) -> str:
    return (
        f"During the durability recheck ({THRESHOLDS.durability_check_days} days later) wind "
        f"gusts reached {weather.max_gust_ms:.1f} m/s (threshold "
        f"{THRESHOLDS.force_majeure_gust_ms:.1f} m/s) and precipitation "
        f"{weather.precipitation_mm:.1f} mm (threshold {THRESHOLDS.force_majeure_precip_mm:.1f} "
        "mm). The measurement is unreliable and force majeure was applied."
    )


def _measurement_id(roof_id: str, phase: str) -> UUID:
    return uuid5(NAMESPACE_DNS, f"{roof_id}-measurement-{phase}")


def _verification_id(roof_id: str, phase: str) -> UUID:
    return uuid5(NAMESPACE_DNS, f"{roof_id}-verification-{phase}")


def _verification_result(
    scenario: DemoScenario, measured_at: datetime, delta_c: float, weather: WeatherValues
) -> VerificationResult:
    # No normalisation model runs on the seed; the raw difference stands in for it.
    status, force_majeure, flags = _decide(delta_c, scenario.coverage_pct, weather)
    reason = (
        _force_majeure_reason(weather)
        if force_majeure
        else _quality_reason(delta_c, scenario.coverage_pct, flags)
    )
    payload = {
        "roof_id": scenario.roof_id,
        "measurement_id": str(_measurement_id(scenario.roof_id, "durability" if force_majeure else "after")),
        "measurement_phase": "durability" if force_majeure else "after",
        "status": status,
        "measured_delta_c": round(delta_c, 2),
        "normalized_delta_c": round(delta_c, 2),
        "coverage_pct": scenario.coverage_pct,
        "anomaly_flags": flags,
        "force_majeure": force_majeure,
        "weather": {
            "ambient_c": weather.ambient_c,
            "radiation_wm2": weather.radiation_wm2,
            "wind_ms": weather.wind_ms,
            "max_gust_ms": weather.max_gust_ms,
            "precipitation_mm": weather.precipitation_mm,
            "window_start": measured_at.isoformat(),
            "window_end": (measured_at + timedelta(hours=1)).isoformat(),
        },
        "measured_at": measured_at.isoformat(),
        "reason": reason,
        # The demo seed is fabricated, never measured.
        "data_source": SIMULATED,
    }
    return VerificationResult(
        **payload,
        evidence_hash=_evidence_hash(payload),
        device_signature=_device_signature(payload, scenario.device_id),
    )


def _verification_row(roof_id: str, phase: str, result: VerificationResult) -> Verification:
    return Verification(
        id=_verification_id(roof_id, phase),
        roof_id=roof_id,
        status=result.status,
        payload=result.model_dump(mode="json"),
        evidence_hash=result.evidence_hash,
        device_signature=result.device_signature,
    )


def _measurement(
    scenario: DemoScenario,
    phase: str,
    curve: Curve,
    measured_at: datetime,
    result: VerificationResult | None,
) -> Measurement:
    # Only the after-coating visit photographs the coating.
    is_after = phase == "after"
    return Measurement(
        id=_measurement_id(scenario.roof_id, phase),
        roof_id=scenario.roof_id,
        phase=phase,
        device_id=scenario.device_id,
        raw_readings=_to_raw_readings(curve, measured_at),
        measured_at=measured_at,
        normalized_delta_c=None if result is None else result.normalized_delta_c,
        anomaly_flags=[] if result is None else result.anomaly_flags,
        photo_path=None,
        coverage_pct=scenario.coverage_pct if is_after else None,
    )


def _weather_row(roof_id: str, timestamp: datetime, weather: WeatherValues) -> WeatherRecord:
    return WeatherRecord(
        roof_id=roof_id,
        timestamp=timestamp,
        ambient_c=weather.ambient_c,
        radiation_wm2=weather.radiation_wm2,
        wind_ms=weather.wind_ms,
        max_gust_ms=weather.max_gust_ms,
        precipitation_mm=weather.precipitation_mm,
        data_source=SIMULATED,
    )


def _pending_tranche(roof_id: str, name: TrancheName) -> ContractState:
    """Always pending, with no transaction: only an escrow event relayed by the oracle may
    move a tranche, so the backend never claims a payment the chain has not made."""
    return ContractState(
        roof_id=roof_id,
        tranche_name=name.value,
        pct=TRANCHE_PERCENTS[name],
        status=TrancheStatus.PENDING.value,
    )


def _phase_times(scenario: DemoScenario, zone: str) -> dict[str, datetime]:
    times = {
        "before": to_utc(scenario.before_local, zone),
        "after": to_utc(scenario.after_local, zone),
    }
    if scenario.storm is not None:
        # Added in local time: the recheck crosses the end of summer time, and adding the
        # days in UTC would move it one wall-clock hour earlier.
        recheck = scenario.after_local + timedelta(days=THRESHOLDS.durability_check_days)
        times["durability"] = to_utc(recheck, zone)
    return times


def _phase_curves(scenario: DemoScenario) -> dict[str, Curve]:
    roof_id = scenario.roof_id
    curves = {
        "before": _rising_plateau_curve(*scenario.before_c, seed=f"{roof_id}-before"),
        "after": _rising_plateau_curve(*scenario.after_c, seed=f"{roof_id}-after"),
    }
    if scenario.storm is not None:
        curves["durability"] = _corrupted_curve(
            scenario.storm.center_c, seed=f"{roof_id}-durability"
        )
    return curves


def _roof(scenario: DemoScenario, zone: str, before_mean: float) -> Roof:
    return Roof(
        id=scenario.roof_id,
        timezone=zone,
        city=DEMO_CITY,
        geom=_square_polygon(scenario.lat, scenario.lon, scenario.area_m2),
        area_m2=scenario.area_m2,
        albedo=scenario.albedo,
        surface_temp_c=round(before_mean, 1),
        priority_score=scenario.priority_score,
        status=scenario.status,
    )


def build_scenario(scenario: DemoScenario) -> DemoRoofRows:
    """Each phase after the first is verified against the phase before it."""
    zone = timezone_for(scenario.lat, scenario.lon)
    times, curves = _phase_times(scenario, zone), _phase_curves(scenario)
    means = {phase: _plateau_mean(curve) for phase, curve in curves.items()}
    rows = DemoRoofRows(roof=_roof(scenario, zone, means["before"]))
    previous = None
    for phase, curve in curves.items():
        weather = scenario.storm.weather if phase == "durability" else scenario.weather
        result = None
        if previous is not None:
            delta_c = means[phase] - means[previous]
            result = _verification_result(scenario, times[phase], delta_c, weather)
            rows.verifications.append(_verification_row(scenario.roof_id, phase, result))
        rows.measurements.append(_measurement(scenario, phase, curve, times[phase], result))
        rows.weather_records.append(_weather_row(scenario.roof_id, times[phase], weather))
        previous = phase
    rows.contract_states.extend(_pending_tranche(scenario.roof_id, name) for name in TrancheName)
    return rows


def build_demo_data() -> list[DemoRoofRows]:
    return [build_scenario(scenario) for scenario in SCENARIOS]
