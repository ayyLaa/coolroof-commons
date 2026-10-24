import re
from collections.abc import Callable
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import (
    MissingMeasurementError,
    MixedDataSourceError,
    RoofNotFoundError,
    WeatherUnavailableError,
)
from app.models import Measurement
from app.repositories.roofs import RoofWithLocation
from app.schemas.verification import EVIDENCE_HASH_PATTERN
from app.services import analysis, verification
from tests.conftest import AFTER_START, ROOF_ID, make_measurement, make_weather, plateau_curve


def make_ml_weather() -> analysis.MlWeather:
    return analysis.MlWeather(ambient_c=34.0, radiation_wm2=850.0, wind_ms=3.0)


@pytest.fixture
def wire(
    monkeypatch: pytest.MonkeyPatch,
    roof: RoofWithLocation,
    weather_lookup: Callable,
    device_address: str,
) -> Callable[..., MagicMock]:
    """Points the service at in-memory fixtures; returns the add_verification spy."""

    def install(before: Measurement | None, after: Measurement | None) -> MagicMock:
        by_phase = {"before": before, "after": after, "durability": after}
        monkeypatch.setattr(
            "app.repositories.roofs.get_roof", lambda _db, rid: roof if rid == ROOF_ID else None
        )
        monkeypatch.setattr(
            "app.repositories.measurements.latest_measurement",
            lambda _db, _rid, phases: by_phase[phases[0]],
        )
        monkeypatch.setattr(
            "app.repositories.measurements.list_other_device_uploads",
            lambda _db, _dev, exclude: [
                m for m in (before, after) if m is not None and m.id != exclude
            ],
        )
        monkeypatch.setattr("app.services.weather.ensure_weather", weather_lookup)
        monkeypatch.setattr("app.repositories.verifications.get_by_evidence_hash", lambda *_: None)
        add_spy = MagicMock()
        monkeypatch.setattr("app.repositories.verifications.add_verification", add_spy)
        return add_spy

    return install


def test_successful_coating_is_approved_and_stored(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement
) -> None:
    add_spy = wire(before, after)

    result = verification.verify_roof(db, ROOF_ID)

    assert result.status == "approved"
    assert result.measured_delta_c == pytest.approx(-13.0, abs=0.2)
    assert result.normalized_delta_c <= -8.0
    assert result.coverage_pct == 94.5
    assert result.anomaly_flags == []
    assert re.fullmatch(EVIDENCE_HASH_PATTERN, result.evidence_hash)
    assert "funds can be released" in result.reason
    add_spy.assert_called_once()
    assert add_spy.call_args.args[1].payload["evidence_hash"] == result.evidence_hash
    db.commit.assert_called_once()


def test_storm_during_measurement_is_force_majeure(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, weather_by_day: dict
) -> None:
    weather_by_day[AFTER_START.date()] = [
        make_weather(AFTER_START, precipitation_mm=68.0, max_gust_ms=24.0),
        make_weather(AFTER_START + timedelta(hours=1)),
    ]
    wire(before, after)

    result = verification.verify_roof(db, ROOF_ID)

    assert result.status == "insufficient_data"
    assert result.force_majeure is True
    assert {"extreme_wind_event", "heavy_precipitation"} <= set(result.anomaly_flags)
    assert result.weather.max_gust_ms == 24.0
    assert result.weather.precipitation_mm == 68.0


def test_old_baseline_storm_does_not_mark_new_measurement_as_storm(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, weather_by_day: dict
) -> None:
    weather_by_day[before.measured_at.date()] = [make_weather(before.measured_at, precipitation_mm=70, max_gust_ms=24)]
    wire(before, after)
    result = verification.verify_roof(db, ROOF_ID)
    assert not result.force_majeure
    assert result.measurement_id == after.id
    assert result.measurement_phase == "after"


def test_multi_hour_rain_sum_is_in_the_signed_verification(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, weather_by_day: dict
) -> None:
    weather_by_day[AFTER_START.date()] = [
        make_weather(AFTER_START, precipitation_mm=30),
        make_weather(AFTER_START + timedelta(hours=1), precipitation_mm=30),
    ]
    wire(before, after)
    result = verification.verify_roof(db, ROOF_ID)
    assert result.force_majeure
    assert result.weather.precipitation_mm == 60
    assert result.weather.window_end - result.weather.window_start == timedelta(hours=2)


def test_single_hour_weather_covers_measurement_seconds(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, weather_by_day: dict
) -> None:
    weather_by_day[AFTER_START.date()] = [make_weather(AFTER_START)]
    wire(before, after)
    result = verification.verify_roof(db, ROOF_ID)
    assert result.weather.window_start <= after.measured_at < result.weather.window_end
    assert result.weather.window_end == AFTER_START + timedelta(hours=1)


def test_frozen_sensor_is_flagged(wire: Callable, db: MagicMock, before: Measurement) -> None:
    frozen = make_measurement("after", AFTER_START, [48.6] * 16, coverage_pct=94.5)
    wire(before, frozen)

    result = verification.verify_roof(db, ROOF_ID)

    assert result.status == "flagged"
    assert "repeated_value" in result.anomaly_flags


def test_unchanged_evidence_is_stored_once(
    wire: Callable,
    db: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    before: Measurement,
    after: Measurement,
) -> None:
    add_spy = wire(before, after)
    monkeypatch.setattr("app.repositories.verifications.get_by_evidence_hash", lambda *_: object())

    verification.verify_roof(db, ROOF_ID)

    add_spy.assert_not_called()


def test_missing_after_measurement_raises(
    wire: Callable, db: MagicMock, before: Measurement
) -> None:
    wire(before, None)

    with pytest.raises(MissingMeasurementError):
        verification.verify_roof(db, ROOF_ID)


def test_unknown_roof_raises(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement
) -> None:
    wire(before, after)

    with pytest.raises(RoofNotFoundError):
        verification.verify_roof(db, "ATH-9999")


def test_no_weather_raises(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, weather_by_day: dict
) -> None:
    weather_by_day.clear()
    wire(before, after)

    with pytest.raises(WeatherUnavailableError):
        verification.verify_roof(db, ROOF_ID)


def test_result_carries_data_source(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement
) -> None:
    wire(before, after)

    assert verification.verify_roof(db, ROOF_ID).data_source == "simulated"


def test_lost_photo_blocks_a_real_measurement_with_passing_numbers(
    wire: Callable, db: MagicMock, before: Measurement, after: Measurement, monkeypatch: pytest.MonkeyPatch
) -> None:
    before.data_source = after.data_source = "measured"
    after.photo_path = "missing/photo.png"
    wire(before, after)
    monkeypatch.setattr("app.services.photos.resolve_photo", lambda _: None)
    result = verification.verify_roof(db, ROOF_ID)
    assert result.status == "insufficient_data"
    assert "no_photo" in result.reason


def test_measured_and_simulated_are_never_compared(
    wire: Callable, db: MagicMock, before: Measurement
) -> None:
    measured_after = make_measurement(
        "after", AFTER_START, [48.0 + i * 0.01 for i in range(16)], data_source="measured"
    )
    wire(before, measured_after)

    with pytest.raises(MixedDataSourceError):
        verification.verify_roof(db, ROOF_ID)


# Regression: normalisation must see the roof's LOCAL hour. The fixtures store
# 10:00 UTC, which is 13:00 in Athens summer.
def test_service_passes_local_hour_to_ml(roof: RoofWithLocation, after: Measurement) -> None:
    observation = analysis.to_observation(after, make_ml_weather(), roof.roof)

    assert analysis.reading_times(after)[-1].hour == 10
    assert observation.local_hour == pytest.approx(13.25)


def test_roof_timezone_changes_the_normalized_delta(
    wire: Callable, db: MagicMock, roof: RoofWithLocation, before: Measurement
) -> None:
    """Before at 13:00 and after at 17:00 local: a timezone error shifts the two hours
    differently through the sun correction, so it no longer cancels in the delta."""
    late_after = make_measurement(
        "after", AFTER_START + timedelta(hours=4), plateau_curve(46.3, 48.6), coverage_pct=94.5
    )
    wire(before, late_after)
    in_athens = verification.verify_roof(db, ROOF_ID).normalized_delta_c

    roof.roof.timezone = "UTC"
    as_if_utc = verification.verify_roof(db, ROOF_ID).normalized_delta_c

    assert in_athens != pytest.approx(as_if_utc, abs=0.05)
