"""Demo before/after curves for one roof: REAL Open-Meteo weather drives the physical
model, but the resulting surface temperatures are SIMULATED and labelled as such."""

from datetime import date, datetime, time

from ml.conditions import InvalidObservationError
from ml.conditions import Weather as MlWeather
from ml.normalization import STANDARD_HOUR_OF_DAY
from ml.synthetic_series import DEMO_SESSION, DEMO_SPIN_UP, generate_before_after_series
from app.repositories.transactions import RepositoryContext, commit

from app.core import timezones
from app.core.config import ASSUMED_COATED_ALBEDO
from app.core.exceptions import RoofNotFoundError, WeatherUnavailableError
from app.repositories import roofs as roof_repo
from app.schemas.series import SimulatedSeriesResponse
from app.services import analysis, weather

DEFAULT_BEFORE_DAY = date(2026, 6, 15)
DEFAULT_AFTER_DAY = date(2026, 7, 15)
# Sessions start at the normalisation's standard hour, so the demo curves line up with
# the conditions every normalised delta is expressed in.
SESSION_LOCAL_TIME = time(int(STANDARD_HOUR_OF_DAY))
PHYSICAL_MODEL = (
    "energy balance (1 - albedo) * radiation = h(wind) * (T_surface - T_ambient), "
    "ml/physical_model.py"
)
WEATHER_SOURCE = "open-meteo hourly weather (real)"


def session_start(day: date, timezone_name: str) -> datetime:
    return timezones.to_utc(datetime.combine(day, SESSION_LOCAL_TIME), timezone_name)


def hourly_weather(db: RepositoryContext, roof_id: str, start: datetime) -> list[tuple[datetime, MlWeather]]:
    window_start, window_end = weather.measurement_window(
        start - DEMO_SPIN_UP, start + DEMO_SESSION
    )
    records = weather.ensure_hourly_coverage(db, roof_id, window_start, window_end)
    return [(record.timestamp, analysis.to_ml_weather(record)) for record in records]


def get_simulated_series(
    db: RepositoryContext, roof_id: str, before_day: date, after_day: date
) -> SimulatedSeriesResponse:
    located = roof_repo.get_roof(db, roof_id)
    if located is None:
        raise RoofNotFoundError(roof_id)
    zone = located.roof.timezone
    before_start, after_start = session_start(before_day, zone), session_start(after_day, zone)
    hourly = sorted(
        hourly_weather(db, roof_id, before_start) + hourly_weather(db, roof_id, after_start)
    )
    commit(db)
    try:
        series = generate_before_after_series(
            hourly, before_start, after_start, located.roof.albedo, ASSUMED_COATED_ALBEDO
        )
    except InvalidObservationError as error:
        raise WeatherUnavailableError(f"Stored weather does not cover the session: {error}")
    return SimulatedSeriesResponse(
        roof_id=roof_id, model=PHYSICAL_MODEL, weather_source=WEATHER_SOURCE, **series
    )
