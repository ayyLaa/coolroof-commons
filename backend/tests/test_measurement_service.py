from collections.abc import Callable
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import (
    MeasurementNotFoundError,
    MissingMeasurementError,
    MixedDataSourceError,
    WeatherUnavailableError,
)
from app.models import Measurement
from app.repositories.roofs import RoofWithLocation
from app.schemas.measurement import MeasurementCreateRequest, MeasurementPhase, Reading
from app.services import measurements
from tests.conftest import AFTER_START, BEFORE_START, DEVICE_ID, ROOF_ID, plateau_curve


def request_for(phase: MeasurementPhase, start, temps: list[float]) -> MeasurementCreateRequest:
    readings = [
        Reading(timestamp=start + timedelta(minutes=i), surface_temp_c=temp)
        for i, temp in enumerate(temps)
    ]
    return MeasurementCreateRequest(
        roof_id=ROOF_ID, phase=phase, readings=readings, device_id=DEVICE_ID
    )


@pytest.fixture
def wire(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation, weather_lookup: Callable
) -> Callable[[Measurement | None], None]:
    def install(existing_before: Measurement | None) -> None:
        monkeypatch.setattr("app.repositories.roofs.get_roof", lambda _db, _rid: roof)
        monkeypatch.setattr(
            "app.repositories.measurements.latest_measurement", lambda *_: existing_before
        )
        monkeypatch.setattr("app.repositories.measurements.add_measurement", lambda _db, m: m)
        monkeypatch.setattr(
            "app.repositories.measurements.list_other_device_uploads", lambda *_: []
        )
        monkeypatch.setattr("app.services.weather.ensure_weather", weather_lookup)

    return install


def test_before_measurement_reports_zero_delta(wire: Callable, db: MagicMock) -> None:
    wire(None)

    response = measurements.create_measurement(
        db, request_for(MeasurementPhase.BEFORE, BEFORE_START, plateau_curve(58.3, 61.6))
    )

    assert response.normalized_delta_c == 0.0
    assert response.anomaly_flags == []
    assert response.data_source == "simulated"
    db.commit.assert_called_once()


def test_after_measurement_is_normalized(
    wire: Callable, db: MagicMock, before: Measurement
) -> None:
    wire(before)

    response = measurements.create_measurement(
        db, request_for(MeasurementPhase.AFTER, AFTER_START, plateau_curve(46.3, 48.6))
    )

    assert response.normalized_delta_c <= -8.0
    assert response.anomaly_flags == []


def test_after_without_before_raises(wire: Callable, db: MagicMock) -> None:
    wire(None)

    with pytest.raises(MissingMeasurementError):
        measurements.create_measurement(
            db, request_for(MeasurementPhase.AFTER, AFTER_START, plateau_curve(46.3, 48.6))
        )


def test_weather_outage_becomes_missing_weather_flag(
    wire: Callable, db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire(None)

    def outage(*_: object) -> list:
        raise WeatherUnavailableError("Open-Meteo request failed")

    monkeypatch.setattr("app.services.weather.ensure_weather", outage)

    response = measurements.create_measurement(
        db, request_for(MeasurementPhase.BEFORE, BEFORE_START, plateau_curve(58.3, 61.6))
    )

    assert "missing_weather" in response.anomaly_flags


def test_photo_for_unknown_measurement_raises(
    db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.repositories.measurements.get_measurement", lambda *_: None)

    with pytest.raises(MeasurementNotFoundError):
        measurements.upload_photo(db, "not-a-uuid", "roof.png", b"")


def test_measured_upload_against_simulated_before_raises(
    wire: Callable, db: MagicMock, before: Measurement
) -> None:
    wire(before)
    payload = request_for(MeasurementPhase.AFTER, AFTER_START, plateau_curve(46.3, 48.6))

    with pytest.raises(MixedDataSourceError):
        measurements.create_measurement(db, payload.model_copy(update={"data_source": "measured"}))
