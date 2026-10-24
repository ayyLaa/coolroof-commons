from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.exceptions import SnapshotFormatError
from app.models import MEASURED, THIRD_PARTY, Roof, WeatherRecord
from app.models.tables import LARGE_ROOF
from app.services import snapshots

GEOJSON = (
    '{"type":"Polygon","coordinates":[[[-0.1,51.5],[-0.09,51.5],[-0.09,51.51],[-0.1,51.5]]]}'
)


def make_roof() -> Roof:
    return Roof(
        id="LON-2064",
        city="London",
        roof_class=LARGE_ROOF,
        status="candidate",
        area_m2=4200.0,
        albedo=0.14,
        surface_temp_c=41.3,
        priority_score=0.77,
        timezone="Europe/London",
        data_source=MEASURED,
        surface_temp_instrument="Landsat 9 TIRS",
        surface_temp_resolution_m=100.0,
    )


def make_weather_record() -> WeatherRecord:
    return WeatherRecord(
        roof_id="LON-2064",
        timestamp=datetime(2026, 7, 15, 11, 0, tzinfo=UTC),
        ambient_c=27.5,
        radiation_wm2=780.0,
        wind_ms=4.1,
        max_gust_ms=9.3,
        precipitation_mm=0.0,
        data_source=THIRD_PARTY,
    )


def test_roofs_survive_an_export_and_import_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "roofs.csv"
    inserted: list[dict] = []
    monkeypatch.setattr(
        "app.repositories.snapshots.list_roofs_with_geojson",
        lambda _db: [(make_roof(), 51.505, -0.095, GEOJSON)],
    )
    monkeypatch.setattr(
        "app.repositories.snapshots.insert_missing_roofs",
        lambda _db, roofs: inserted.extend(roofs) or len(roofs),
    )

    assert snapshots.export_roofs(None, path) == 1
    assert snapshots.import_roofs(None, path) == 1

    assert inserted[0]["id"] == "LON-2064"
    assert inserted[0]["surface_temp_instrument"] == "Landsat 9 TIRS"
    assert inserted[0]["surface_temp_resolution_m"] == 100.0
    assert inserted[0]["geometry"] == GEOJSON


def test_weather_import_keeps_stored_hours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "weather.csv"
    calls: list[tuple[str, list[dict], bool]] = []
    monkeypatch.setattr(
        "app.repositories.snapshots.list_weather", lambda _db, _ids, _src: [make_weather_record()]
    )
    monkeypatch.setattr(
        "app.repositories.weather.upsert_hourly",
        lambda _db, roof_id, records, overwrite: calls.append((roof_id, records, overwrite)),
    )

    snapshots.export_weather(None, path, ["LON-2064"])

    assert snapshots.import_weather(None, path) == 1
    roof_id, records, overwrite = calls[0]
    assert (roof_id, overwrite) == ("LON-2064", False)
    assert records[0]["timestamp"] == datetime(2026, 7, 15, 11, 0, tzinfo=UTC)


def test_row_without_geometry_is_rejected() -> None:
    row = snapshots.roof_to_csv_row(make_roof(), 51.5, -0.1, "")
    text_row = {key: str(value) for key, value in row.items()}

    with pytest.raises(SnapshotFormatError, match="geometry"):
        snapshots.parse_roof_row(text_row)


def test_timestamp_without_offset_is_rejected() -> None:
    exported = snapshots.weather_to_csv_row(make_weather_record())
    row = {key: str(value) for key, value in exported.items()}
    row["timestamp"] = "2026-07-15T11:00:00"

    with pytest.raises(SnapshotFormatError, match="UTC offset"):
        snapshots.parse_weather_row(row)
