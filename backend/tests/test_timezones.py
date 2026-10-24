from datetime import UTC, datetime

import pytest

from app.core.exceptions import TimezoneError
from app.core.timezones import timezone_for, to_local, to_utc

ATHENS = "Europe/Athens"


def test_timezone_from_athens_location() -> None:
    assert timezone_for(37.9838, 23.7275) == ATHENS


def test_summer_and_winter_offsets() -> None:
    summer = to_local(datetime(2026, 7, 15, 10, 0, tzinfo=UTC), ATHENS)
    winter = to_local(datetime(2027, 1, 21, 10, 0, tzinfo=UTC), ATHENS)

    assert summer.hour == 13
    assert winter.hour == 12


def test_round_trip_through_local_wall_clock() -> None:
    utc = to_utc(datetime(2026, 7, 15, 13, 0), ATHENS)

    assert utc == datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    assert to_local(utc, ATHENS).replace(tzinfo=None) == datetime(2026, 7, 15, 13, 0)


def test_naive_datetime_cannot_be_localised() -> None:
    with pytest.raises(TimezoneError):
        to_local(datetime(2026, 7, 15, 10, 0), ATHENS)


def test_location_without_timezone_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.timezones._finder",
        lambda: type("F", (), {"timezone_at": lambda *_, **__: None})(),
    )

    with pytest.raises(TimezoneError):
        timezone_for(0.0, 0.0)
