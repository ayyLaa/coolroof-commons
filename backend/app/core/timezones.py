"""Timezone helpers. Everything is stored in UTC; local time exists only on the way into
normalisation, where the hour of day stands in for the sun's position."""

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from app.core.exceptions import TimezoneError


@lru_cache(maxsize=1)
def _finder() -> TimezoneFinder:
    """Loading the boundary data is slow; one instance serves the whole process."""
    return TimezoneFinder()


def timezone_for(lat: float, lon: float) -> str:
    name = _finder().timezone_at(lat=lat, lng=lon)
    if name is None:
        raise TimezoneError(f"No IANA timezone found for ({lat}, {lon}).")
    return name


def to_local(moment: datetime, timezone_name: str) -> datetime:
    """moment must be timezone-aware: a naive datetime is ambiguous, and guessing UTC
    is exactly the silent shift this module exists to prevent."""
    if moment.tzinfo is None:
        raise TimezoneError(f"Naive datetime {moment.isoformat()} cannot be localised.")
    return moment.astimezone(ZoneInfo(timezone_name))


def to_utc(moment: datetime, timezone_name: str) -> datetime:
    """A naive moment is read as wall-clock time in timezone_name (DST included)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(timezone_name))
    return moment.astimezone(UTC)
