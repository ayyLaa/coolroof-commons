from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.exceptions import WeatherUnavailableError
from app.infrastructure.clients import open_meteo

START = date(2026, 7, 1)


def hourly_payload() -> dict:
    return {"hourly": {
        "time": ["2026-07-01T10:00", "2026-07-01T11:00"],
        **{name: [1.0, None] for name in open_meteo.COLUMN_BY_VARIABLE},
    }}


def test_fetch_hourly_parses_utc_and_drops_missing_values(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.return_value = hourly_payload()
    get = MagicMock(return_value=response)
    monkeypatch.setattr(open_meteo.httpx, "get", get)

    rows = open_meteo.fetch_hourly(37.98, 23.73, START, START)

    assert len(rows) == 1
    assert rows[0]["timestamp"] == datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
    assert rows[0]["wind_ms"] == 1.0
    assert get.call_args.kwargs["params"]["wind_speed_unit"] == "ms"
    response.raise_for_status.assert_called_once()


def test_http_failure_is_a_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(open_meteo.httpx, "get", MagicMock(side_effect=httpx.ConnectError("offline")))
    with pytest.raises(WeatherUnavailableError, match="request failed"):
        open_meteo.fetch_hourly(37.98, 23.73, START, START)


@pytest.mark.parametrize("payload", [{}, {"hourly": {"time": ["bad"]}}, None])
def test_malformed_response_is_a_domain_error(payload: object, monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.return_value = payload
    monkeypatch.setattr(open_meteo.httpx, "get", MagicMock(return_value=response))
    with pytest.raises(WeatherUnavailableError, match="invalid hourly"):
        open_meteo.fetch_hourly(37.98, 23.73, START, START)


def test_archive_boundary() -> None:
    today = date(2026, 7, 10)
    assert open_meteo.choose_endpoint(date(2026, 7, 5), today) == open_meteo.ARCHIVE_URL
    assert open_meteo.choose_endpoint(date(2026, 7, 6), today) == open_meteo.FORECAST_URL
