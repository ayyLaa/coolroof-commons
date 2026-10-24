from datetime import date, datetime, time, timedelta, timezone

from app.repositories.transactions import RepositoryContext, commit

from app.core.exceptions import RoofNotFoundError
from app.repositories.records import WeatherData, weather_data
from app.repositories import roofs as roof_repo
from app.repositories import weather as weather_repo
from app.schemas.weather import WeatherPoint
from app.infrastructure.clients import open_meteo

# Records are hourly; padding the window by one hour on each side guarantees the hour
# containing the measurement and its neighbour are both available.
WINDOW_PADDING = timedelta(hours=1)
HOUR = timedelta(hours=1)


def measurement_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    return start - WINDOW_PADDING, end + WINDOW_PADDING


def ensure_weather(
    db: RepositoryContext, roof_id: str, start: datetime, end: datetime
) -> list[WeatherData]:
    """Stored hours are used as-is; only an empty window triggers an Open-Meteo request,
    whose result is stored so the same hours are never fetched again."""
    records = [weather_data(row) for row in weather_repo.list_in_range(db, roof_id, start, end)]
    if records:
        return records
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    fetched = open_meteo.fetch_hourly(located.lat, located.lon, start.date(), end.date())
    weather_repo.upsert_hourly(db, roof_id, fetched)
    return [weather_data(row) for row in weather_repo.list_in_range(db, roof_id, start, end)]


def expected_hours(start: datetime, end: datetime) -> int:
    first = start.replace(minute=0, second=0, microsecond=0)
    if first < start:
        first += HOUR
    return max(0, int((end - first) // HOUR) + 1)


def ensure_hourly_coverage(
    db: RepositoryContext, roof_id: str, start: datetime, end: datetime
) -> list[WeatherData]:
    """Unlike ensure_weather, a partially stored window is completed from Open-Meteo;
    only missing hours are added, so stored rows are never replaced."""
    records = [weather_data(row) for row in weather_repo.list_in_range(db, roof_id, start, end)]
    if len(records) >= expected_hours(start, end):
        return records
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    fetched = open_meteo.fetch_hourly(located.lat, located.lon, start.date(), end.date())
    weather_repo.upsert_hourly(db, roof_id, fetched, overwrite=False)
    return [weather_data(row) for row in weather_repo.list_in_range(db, roof_id, start, end)]


def nearest_record(records: list[WeatherData], moment: datetime) -> WeatherData | None:
    if not records:
        return None
    return min(records, key=lambda record: abs(record.timestamp - moment))


def to_weather_point(record: WeatherData) -> WeatherPoint:
    return WeatherPoint(
        timestamp=record.timestamp,
        ambient_c=record.ambient_c,
        radiation_wm2=record.radiation_wm2,
        wind_ms=record.wind_ms,
        max_gust_ms=record.max_gust_ms,
        precipitation_mm=record.precipitation_mm,
        data_source=record.data_source,
    )


def get_weather_history(db: RepositoryContext, roof_id: str, start: date, end: date) -> list[WeatherPoint]:
    if roof_repo.get_roof(db, roof_id) is None:
        raise RoofNotFoundError(roof_id)
    window_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(end, time.max, tzinfo=timezone.utc)
    records = ensure_weather(db, roof_id, window_start, window_end)
    commit(db)
    return [to_weather_point(record) for record in records]
