"""CoolRoof Commons - loads hourly Open-Meteo weather for roofs into weather_records.

Verification normalises surface temperatures against real ambient conditions and
detects force majeure (gusts, rain), so it needs measured weather, not constants.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.exceptions import RoofNotFoundError  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Roof, WeatherRecord  # noqa: E402
from cities import CITIES, City, add_city_argument  # noqa: E402

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARIABLES = (
    "temperature_2m",
    "shortwave_radiation",
    "wind_speed_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "precipitation",
)
# cloud_cover has no weather_records column; it is fetched and kept in the cache only.
COLUMN_BY_VARIABLE = {
    "temperature_2m": "ambient_c",
    "shortwave_radiation": "radiation_wm2",
    "wind_speed_10m": "wind_ms",
    "wind_gusts_10m": "max_gust_ms",
    "precipitation": "precipitation_mm",
}
# The archive (ERA5) trails real time by about five days; newer ranges need the forecast API.
ARCHIVE_DELAY_DAYS = 5
# ~1 km, finer than the weather model grid, so neighbouring roofs share one cached request.
COORDINATE_DECIMALS = 2
REQUEST_TIMEOUT_S = 30.0
CACHE_DIR = REPO_ROOT / "data" / "cache" / "open_meteo"
SOURCES = ("auto", "forecast", "archive")


def choose_endpoint(source: str, end_date: date, today: date) -> str:
    if source == "forecast":
        return FORECAST_URL
    if source == "archive":
        return ARCHIVE_URL
    archive_available_until = today - timedelta(days=ARCHIVE_DELAY_DAYS)
    return ARCHIVE_URL if end_date <= archive_available_until else FORECAST_URL


def build_query(lat: float, lon: float, start_date: date, end_date: date) -> dict[str, str]:
    return {
        "latitude": f"{lat:.{COORDINATE_DECIMALS}f}",
        "longitude": f"{lon:.{COORDINATE_DECIMALS}f}",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    }


def cache_path_for(url: str, params: dict[str, str]) -> Path:
    key = json.dumps({"url": url, "params": params}, sort_keys=True)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()}.json"


def fetch_hourly(url: str, params: dict[str, str], refresh: bool) -> dict:
    cache_path = cache_path_for(url, params)
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    payload = response.json()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def parse_hourly_records(payload: dict) -> list[dict]:
    """Hours with any missing value are dropped: every weather_records column is NOT NULL
    and a guessed value would silently distort normalisation."""
    hourly = payload["hourly"]
    records = []
    for index, raw_time in enumerate(hourly["time"]):
        values = {column: hourly[var][index] for var, column in COLUMN_BY_VARIABLE.items()}
        if any(value is None for value in values.values()):
            continue
        timestamp = datetime.fromisoformat(raw_time).replace(tzinfo=timezone.utc)
        records.append({"timestamp": timestamp, **values})
    return records


def load_roof_locations(
    session: Session, roof_ids: list[str], city: City
) -> list[tuple[str, float, float]]:
    """Explicit roof ids win over the city filter, so any roof can be refreshed directly."""
    centroid = func.ST_Centroid(Roof.geom)
    query = session.query(Roof.id, func.ST_Y(centroid), func.ST_X(centroid)).filter(
        Roof.geom.isnot(None)
    )
    if roof_ids:
        query = query.filter(Roof.id.in_(roof_ids))
    else:
        query = query.filter(Roof.city == city.name)
    locations = [(roof_id, lat, lon) for roof_id, lat, lon in query.order_by(Roof.id)]
    missing = set(roof_ids) - {roof_id for roof_id, _, _ in locations}
    if missing:
        raise RoofNotFoundError(", ".join(sorted(missing)))
    return locations


def upsert_weather_records(session: Session, roof_id: str, records: list[dict]) -> int:
    """weather_records has no (roof_id, timestamp) unique constraint, so the upsert matches
    existing hours in Python instead of relying on ON CONFLICT."""
    if not records:
        return 0
    timestamps = [record["timestamp"] for record in records]
    existing_rows = session.query(WeatherRecord).filter(
        WeatherRecord.roof_id == roof_id,
        WeatherRecord.timestamp.between(min(timestamps), max(timestamps)),
    )
    existing = {row.timestamp: row for row in existing_rows}
    for record in records:
        row = existing.get(record["timestamp"])
        if row is None:
            session.add(WeatherRecord(roof_id=roof_id, **record))
            continue
        for column, value in record.items():
            setattr(row, column, value)
    return len(records)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch hourly Open-Meteo weather for roofs.")
    add_city_argument(parser)
    parser.add_argument(
        "--start", type=date.fromisoformat, help="YYYY-MM-DD; defaults to the city's summer start."
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, help="YYYY-MM-DD; defaults to the city's summer end."
    )
    parser.add_argument("--source", choices=SOURCES, default="auto", help="API endpoint to use.")
    parser.add_argument(
        "--roof-id", action="append", default=[], dest="roof_ids",
        help="Roof to fetch for; repeatable. Defaults to every roof of --city.",
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore the file cache.")
    args = parser.parse_args()
    city = CITIES[args.city]
    args.start = args.start or date.fromisoformat(city.summer[0])
    args.end = args.end or date.fromisoformat(city.summer[1])
    if args.start > args.end:
        parser.error("--start must not be after --end.")
    return args


def main() -> None:
    args = parse_args()
    url = choose_endpoint(args.source, args.end, datetime.now(timezone.utc).date())
    print(f"Using {url} for {args.start} .. {args.end}.")
    with SessionLocal() as session:
        for roof_id, lat, lon in load_roof_locations(session, args.roof_ids, CITIES[args.city]):
            payload = fetch_hourly(url, build_query(lat, lon, args.start, args.end), args.refresh)
            written = upsert_weather_records(session, roof_id, parse_hourly_records(payload))
            print(f"{roof_id}: {written} hourly records upserted.")
        session.commit()


if __name__ == "__main__":
    main()
