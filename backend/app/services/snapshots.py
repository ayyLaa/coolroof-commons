"""CSV snapshots of the roofs and the demo weather.

The measured roofs come from hours of Earth Engine work, so a committed copy lets an
empty database (a fresh docker compose volume) be refilled without it.
"""

import csv
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from app.repositories.transactions import RepositoryContext

from app.core.exceptions import SnapshotFormatError
from app.models import THIRD_PARTY, Roof, WeatherRecord
from app.repositories import snapshots as snapshot_repo
from app.repositories import weather as weather_repo

ROOF_COLUMNS = (
    "roof_id",
    "city",
    "roof_class",
    "status",
    "lat",
    "lon",
    "area_m2",
    "albedo",
    "surface_temp_c",
    "priority_score",
    "timezone",
    "data_source",
    "instrument",
    "instrument_resolution_m",
    "geometry",
)
WEATHER_COLUMNS = (
    "roof_id",
    "timestamp",
    "ambient_c",
    "radiation_wm2",
    "wind_ms",
    "max_gust_ms",
    "precipitation_mm",
    "data_source",
)
WEATHER_VALUE_COLUMNS = ("ambient_c", "radiation_wm2", "wind_ms", "max_gust_ms", "precipitation_mm")


def roof_to_csv_row(roof: Roof, lat: float, lon: float, geojson: str) -> dict[str, object]:
    """lat and lon are the centroid, for reading the file; import rebuilds from geometry."""
    return {
        "roof_id": roof.id,
        "city": roof.city,
        "roof_class": roof.roof_class,
        "status": roof.status,
        "lat": lat,
        "lon": lon,
        "area_m2": roof.area_m2,
        "albedo": roof.albedo,
        "surface_temp_c": roof.surface_temp_c,
        "priority_score": roof.priority_score,
        "timezone": roof.timezone,
        "data_source": roof.data_source,
        "instrument": roof.surface_temp_instrument or "",
        "instrument_resolution_m": _blank_if_none(roof.surface_temp_resolution_m),
        "geometry": geojson,
    }


def weather_to_csv_row(record: WeatherRecord) -> dict[str, object]:
    return {
        "roof_id": record.roof_id,
        "timestamp": record.timestamp.isoformat(),
        **{column: getattr(record, column) for column in WEATHER_VALUE_COLUMNS},
        "data_source": record.data_source,
    }


def parse_roof_row(row: dict[str, str]) -> dict[str, object]:
    return _parse(row, lambda: {
        "id": _required(row, "roof_id"),
        "city": _required(row, "city"),
        "roof_class": _required(row, "roof_class"),
        "status": _required(row, "status"),
        "area_m2": float(row["area_m2"]),
        "albedo": float(row["albedo"]),
        "surface_temp_c": float(row["surface_temp_c"]),
        "priority_score": float(row["priority_score"]),
        "timezone": _required(row, "timezone"),
        "data_source": _required(row, "data_source"),
        "surface_temp_instrument": row["instrument"] or None,
        "surface_temp_resolution_m": _float_or_none(row["instrument_resolution_m"]),
        "geometry": _required(row, "geometry"),
    })


def parse_weather_row(row: dict[str, str]) -> dict[str, object]:
    return _parse(row, lambda: {
        "timestamp": _aware_timestamp(row["timestamp"]),
        **{column: float(row[column]) for column in WEATHER_VALUE_COLUMNS},
        "data_source": _required(row, "data_source"),
    })


def export_roofs(db: RepositoryContext, path: Path) -> int:
    rows = [roof_to_csv_row(*row) for row in snapshot_repo.list_roofs_with_geojson(db)]
    _write_csv(path, ROOF_COLUMNS, rows)
    return len(rows)


def export_weather(db: RepositoryContext, path: Path, roof_ids: Sequence[str]) -> int:
    """Only Open-Meteo rows: the demo seed rebuilds its own simulated weather."""
    records = snapshot_repo.list_weather(db, roof_ids, THIRD_PARTY)
    _write_csv(path, WEATHER_COLUMNS, [weather_to_csv_row(record) for record in records])
    return len(records)


def import_roofs(db: RepositoryContext, path: Path) -> int:
    """Returns how many roofs were new; the caller commits."""
    return snapshot_repo.insert_missing_roofs(db, [parse_roof_row(row) for row in _read_csv(path)])


def import_weather(db: RepositoryContext, path: Path) -> int:
    """Hours already stored are kept, so importing twice adds nothing; the caller commits."""
    by_roof: dict[str, list[dict]] = defaultdict(list)
    for row in _read_csv(path):
        by_roof[_required(row, "roof_id")].append(parse_weather_row(row))
    for roof_id, records in by_roof.items():
        weather_repo.upsert_hourly(db, roof_id, records, overwrite=False)
    return sum(len(records) for records in by_roof.values())


def _write_csv(path: Path, columns: Sequence[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _parse(row: dict[str, str], build: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return build()
    except (KeyError, ValueError) as error:
        raise SnapshotFormatError(f"Invalid snapshot row {row.get('roof_id')!r}: {error}") from error


def _required(row: dict[str, str], column: str) -> str:
    value = row[column]
    if not value:
        raise ValueError(f"{column} is empty")
    return value


def _aware_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp {value} has no UTC offset")
    return timestamp


def _float_or_none(value: str) -> float | None:
    return float(value) if value else None


def _blank_if_none(value: float | None) -> float | str:
    return "" if value is None else value
