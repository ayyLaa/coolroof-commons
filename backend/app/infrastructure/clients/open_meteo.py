"""Outbound Open-Meteo client used when weather_records lacks the hours a measurement
needs. The database is the cache: fetched hours are stored and never requested twice."""

from datetime import date, datetime, timedelta, timezone

import httpx

from app.core.exceptions import WeatherUnavailableError

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# The archive (ERA5) trails real time by about five days; newer ranges need the forecast API.
ARCHIVE_DELAY_DAYS = 5
REQUEST_TIMEOUT_S = 30.0
COLUMN_BY_VARIABLE = {
    "temperature_2m": "ambient_c",
    "shortwave_radiation": "radiation_wm2",
    "wind_speed_10m": "wind_ms",
    "wind_gusts_10m": "max_gust_ms",
    "precipitation": "precipitation_mm",
}


def choose_endpoint(end_date: date, today: date) -> str:
    archive_available_until = today - timedelta(days=ARCHIVE_DELAY_DAYS)
    return ARCHIVE_URL if end_date <= archive_available_until else FORECAST_URL


def parse_hourly(payload: dict) -> list[dict]:
    """Hours with a missing value are dropped: weather_records columns are NOT NULL and
    a guessed value would silently distort normalisation."""
    hourly = payload["hourly"]
    records = []
    for index, raw_time in enumerate(hourly["time"]):
        values = {column: hourly[var][index] for var, column in COLUMN_BY_VARIABLE.items()}
        if any(value is None for value in values.values()):
            continue
        timestamp = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
        records.append({"timestamp": timestamp, **values})
    return records


def fetch_hourly(lat: float, lon: float, start_date: date, end_date: date) -> list[dict]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(COLUMN_BY_VARIABLE),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }
    url = choose_endpoint(end_date, datetime.now(timezone.utc).date())
    try:
        response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise WeatherUnavailableError(f"Open-Meteo request failed: {error}") from error
    try:
        return parse_hourly(response.json())
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise WeatherUnavailableError("Open-Meteo returned invalid hourly weather data.") from error
