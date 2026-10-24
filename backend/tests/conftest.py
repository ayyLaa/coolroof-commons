"""Fixtures build unsaved ORM objects and fake the repository layer, so service tests
run without a database, Open-Meteo or a real device key."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from eth_account import Account

from app.models import SIMULATED, THIRD_PARTY, Measurement, Roof, WeatherRecord
from app.models.tables import SMALL_ROOF
from app.repositories.roofs import RoofWithLocation

TEST_PRIVATE_KEY = "0x" + "11" * 32
ATHENS = "Europe/Athens"
ROOF_ID = "ATH-0142"
DEVICE_ID = "DEV-0391"
BEFORE_START = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
AFTER_START = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
CLEAR_DAY = {"ambient_c": 34.0, "radiation_wm2": 850.0, "wind_ms": 3.0, "max_gust_ms": 6.0}
WARMUP_RATE = 0.35
ROOF_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[23.73, 37.98], [23.731, 37.98], [23.731, 37.981], [23.73, 37.98]]],
}
READING_COUNT = 16


@pytest.fixture(autouse=True)
def isolate_external_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVENT_RPC_URL", raising=False)
    monkeypatch.delenv("WRITE_API_KEY", raising=False)
    monkeypatch.delenv("EVENT_API_KEY", raising=False)
    monkeypatch.setenv("APP_MODE", "local")


def plateau_curve(start_c: float, plateau_c: float) -> list[float]:
    return [
        round(start_c + (plateau_c - start_c) * (1 - math.exp(-WARMUP_RATE * t)), 2)
        for t in range(READING_COUNT)
    ]


def make_measurement(
    phase: str, start: datetime, temps: list[float], **extra: object
) -> Measurement:
    readings = [
        {"timestamp": (start + timedelta(minutes=i)).isoformat(), "surface_temp_c": temp}
        for i, temp in enumerate(temps)
    ]
    return Measurement(
        id=uuid4(),
        roof_id=ROOF_ID,
        phase=phase,
        device_id=DEVICE_ID,
        raw_readings=readings,
        measured_at=start,
        anomaly_flags=[],
        **{"data_source": SIMULATED, **extra},
    )


def make_weather(
    moment: datetime, precipitation_mm: float = 0.0, **overrides: float
) -> WeatherRecord:
    values = {**CLEAR_DAY, **overrides}
    return WeatherRecord(
        id=uuid4(),
        roof_id=ROOF_ID,
        timestamp=moment,
        precipitation_mm=precipitation_mm,
        data_source=THIRD_PARTY,
        **values,
    )


@pytest.fixture
def roof() -> RoofWithLocation:
    model = Roof(
        id=ROOF_ID,
        city="Athens",
        roof_class=SMALL_ROOF,
        area_m2=850.0,
        albedo=0.12,
        surface_temp_c=61.6,
        priority_score=0.9,
        status="measuring",
        data_source=SIMULATED,
        timezone=ATHENS,
    )
    return RoofWithLocation(roof=model, lat=37.98, lon=23.73, geometry=ROOF_POLYGON)


@pytest.fixture
def before() -> Measurement:
    return make_measurement("before", BEFORE_START, plateau_curve(58.3, 61.6))


@pytest.fixture
def after() -> Measurement:
    return make_measurement("after", AFTER_START, plateau_curve(46.3, 48.6), coverage_pct=94.5)


@pytest.fixture
def weather_by_day() -> dict[datetime, list[WeatherRecord]]:
    """Two hourly records around each measurement, keyed by the measurement's date."""
    return {
        start.date(): [make_weather(start), make_weather(start + timedelta(hours=1))]
        for start in (BEFORE_START, AFTER_START)
    }


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def device_address(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.services.evidence.DEVICE_PRIVATE_KEY", TEST_PRIVATE_KEY)
    return Account.from_key(TEST_PRIVATE_KEY).address


@pytest.fixture
def weather_lookup(
    weather_by_day: dict,
) -> Callable[[object, str, datetime, datetime], list[WeatherRecord]]:
    def lookup(_db: object, _roof_id: str, start: datetime, _end: datetime) -> list[WeatherRecord]:
        return weather_by_day.get(start.date(), [])

    return lookup
