from collections.abc import Callable
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import RoofNotFoundError, WeatherUnavailableError
from app.models import WeatherRecord
from app.repositories.roofs import RoofWithLocation
from app.services import series
from app.services.weather import expected_hours
from tests.conftest import ROOF_ID, make_weather

BEFORE_DAY = date(2026, 6, 15)
AFTER_DAY = date(2026, 7, 15)


def hourly_records(start: datetime, end: datetime) -> list[WeatherRecord]:
    first = start.replace(minute=0, second=0, microsecond=0)
    hours = int((end - first) / timedelta(hours=1)) + 1
    return [make_weather(first + timedelta(hours=h)) for h in range(hours)]


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation) -> Callable[[Callable], None]:
    def install(weather_lookup: Callable) -> None:
        monkeypatch.setattr(
            "app.repositories.roofs.get_roof", lambda _db, rid: roof if rid == ROOF_ID else None
        )
        monkeypatch.setattr("app.services.weather.ensure_hourly_coverage", weather_lookup)

    return install


def test_series_is_simulated_from_real_weather(wire: Callable, db: MagicMock) -> None:
    wire(lambda _db, _rid, start, end: hourly_records(start, end))

    response = series.get_simulated_series(db, ROOF_ID, BEFORE_DAY, AFTER_DAY)

    assert response.data_source == "simulated"
    assert "real" in response.weather_source
    for phase in (response.before, response.after):
        assert len(phase.readings) == 31
        assert {reading.data_source for reading in phase.readings} == {"simulated"}
    assert response.before.start.hour == 10  # 13:00 in Athens summer time
    assert response.after.readings[0].surface_temp_c < response.before.readings[0].surface_temp_c


def test_incomplete_weather_raises(wire: Callable, db: MagicMock) -> None:
    wire(lambda _db, _rid, start, _end: [make_weather(start)])

    with pytest.raises(WeatherUnavailableError):
        series.get_simulated_series(db, ROOF_ID, BEFORE_DAY, AFTER_DAY)


def test_unknown_roof_raises(wire: Callable, db: MagicMock) -> None:
    wire(lambda *_: [])

    with pytest.raises(RoofNotFoundError):
        series.get_simulated_series(db, "ATH-9999", BEFORE_DAY, AFTER_DAY)


@pytest.mark.parametrize(
    ("start", "end", "hours"),
    [
        (datetime(2026, 7, 15, 9, 0), datetime(2026, 7, 15, 11, 15), 3),
        (datetime(2026, 7, 15, 9, 30), datetime(2026, 7, 15, 11, 15), 2),
        (datetime(2026, 7, 15, 9, 30), datetime(2026, 7, 15, 9, 45), 0),
    ],
)
def test_expected_hours(start: datetime, end: datetime, hours: int) -> None:
    assert expected_hours(start, end) == hours
