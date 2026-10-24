from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import RoofNotFoundError, WeatherUnavailableError
from app.repositories.roofs import RoofWithLocation
from app.services import weather
from tests.conftest import AFTER_START, ROOF_ID, make_weather


def test_cached_weather_skips_http(db: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    records = [make_weather(AFTER_START)]
    monkeypatch.setattr(weather.weather_repo, "list_in_range", lambda *_: records)
    fetch = MagicMock()
    monkeypatch.setattr(weather.open_meteo, "fetch_hourly", fetch)
    result = weather.ensure_weather(db, ROOF_ID, AFTER_START, AFTER_START)
    assert [point.timestamp for point in result] == [AFTER_START]
    assert result[0].data_source == "third_party"
    fetch.assert_not_called()


def test_missing_weather_is_fetched_and_stored(
    db: MagicMock, roof: RoofWithLocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [make_weather(AFTER_START)]
    monkeypatch.setattr(weather.weather_repo, "list_in_range", MagicMock(side_effect=[[], records]))
    monkeypatch.setattr(weather.roof_repo, "get_roof", lambda *_: roof)
    fetched = [{"timestamp": AFTER_START}]
    fetch = MagicMock(return_value=fetched)
    upsert = MagicMock()
    monkeypatch.setattr(weather.open_meteo, "fetch_hourly", fetch)
    monkeypatch.setattr(weather.weather_repo, "upsert_hourly", upsert)
    assert [point.timestamp for point in weather.ensure_weather(db, ROOF_ID, AFTER_START, AFTER_START)] == [AFTER_START]
    fetch.assert_called_once_with(roof.lat, roof.lon, AFTER_START.date(), AFTER_START.date())
    upsert.assert_called_once_with(db, ROOF_ID, fetched)


def test_unknown_roof_does_not_fetch(db: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(weather.weather_repo, "list_in_range", lambda *_: [])
    monkeypatch.setattr(weather.roof_repo, "get_roof", lambda *_: None)
    fetch = MagicMock()
    monkeypatch.setattr(weather.open_meteo, "fetch_hourly", fetch)
    with pytest.raises(RoofNotFoundError):
        weather.ensure_weather(db, ROOF_ID, AFTER_START, AFTER_START)
    fetch.assert_not_called()


def test_failed_fetch_does_not_persist(
    db: MagicMock, roof: RoofWithLocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(weather.weather_repo, "list_in_range", lambda *_: [])
    monkeypatch.setattr(weather.roof_repo, "get_roof", lambda *_: roof)
    monkeypatch.setattr(weather.open_meteo, "fetch_hourly", MagicMock(side_effect=WeatherUnavailableError("offline")))
    upsert = MagicMock()
    monkeypatch.setattr(weather.weather_repo, "upsert_hourly", upsert)
    with pytest.raises(WeatherUnavailableError):
        weather.ensure_weather(db, ROOF_ID, AFTER_START, AFTER_START)
    upsert.assert_not_called()


def test_partial_coverage_keeps_existing_rows(
    db: MagicMock, roof: RoofWithLocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = [make_weather(AFTER_START)]
    complete = [*one, make_weather(AFTER_START + timedelta(hours=1))]
    monkeypatch.setattr(weather.weather_repo, "list_in_range", MagicMock(side_effect=[one, complete]))
    monkeypatch.setattr(weather.roof_repo, "get_roof", lambda *_: roof)
    monkeypatch.setattr(weather.open_meteo, "fetch_hourly", lambda *_: [])
    upsert = MagicMock()
    monkeypatch.setattr(weather.weather_repo, "upsert_hourly", upsert)
    result = weather.ensure_hourly_coverage(db, ROOF_ID, AFTER_START, AFTER_START + timedelta(hours=1))
    assert [point.timestamp for point in result] == [AFTER_START, AFTER_START + timedelta(hours=1)]
    upsert.assert_called_once_with(db, ROOF_ID, [], overwrite=False)


def test_history_commits_fetched_weather(
    db: MagicMock, roof: RoofWithLocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(weather.roof_repo, "get_roof", lambda *_: roof)
    monkeypatch.setattr(weather, "ensure_weather", lambda *_: [make_weather(AFTER_START)])
    points = weather.get_weather_history(db, ROOF_ID, date(2026, 7, 15), date(2026, 7, 15))
    assert points[0].timestamp == AFTER_START
    db.commit.assert_called_once()
