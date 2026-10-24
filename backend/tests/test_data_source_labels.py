from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.models import SIMULATED, THIRD_PARTY
from app.repositories.roofs import RoofWithLocation
from app.schemas.measurement import MeasurementCreateRequest
from app.services import weather
from tests.conftest import ROOF_ID, make_weather

READING = {"timestamp": "2026-07-15T10:00:00Z", "surface_temp_c": 48.0}


def request(**extra: object) -> MeasurementCreateRequest:
    return MeasurementCreateRequest(
        roof_id=ROOF_ID, phase="after", device_id="DEV-0391", readings=[READING], **extra
    )


def test_upload_defaults_to_simulated() -> None:
    assert request().data_source == "simulated"


def test_upload_accepts_measured() -> None:
    assert request(data_source="measured").data_source == "measured"


def test_upload_rejects_third_party() -> None:
    with pytest.raises(ValidationError):
        request(data_source="third_party")


def test_weather_points_keep_their_own_label(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation
) -> None:
    open_meteo = make_weather(datetime(2026, 7, 15, 10, tzinfo=UTC))
    open_meteo.data_source = THIRD_PARTY
    seeded = make_weather(datetime(2026, 7, 15, 11, tzinfo=UTC))
    seeded.data_source = SIMULATED
    monkeypatch.setattr("app.repositories.roofs.get_roof", lambda *_: roof)
    monkeypatch.setattr(weather, "ensure_weather", lambda *_: [open_meteo, seeded])

    points = weather.get_weather_history(MagicMock(), ROOF_ID, date(2026, 7, 15), date(2026, 7, 15))

    assert [point.data_source for point in points] == ["third_party", "simulated"]
