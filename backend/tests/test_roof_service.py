from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.repositories.roofs import RoofWithLocation
from app.services import roofs as roof_service


def test_list_roofs_passes_city_filter(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation
) -> None:
    calls = []

    def fake_list(
        _db: object, city: str | None, min_score: float | None, page: tuple, geometry: bool
    ) -> list:
        calls.append((city, min_score, page, geometry))
        return [roof] if city == "London" else []

    monkeypatch.setattr("app.repositories.roofs.list_roofs", fake_list)

    london = roof_service.list_roofs(
        None, city="London", page=(50, 0), min_score=None, include_geometry=True
    )
    paris = roof_service.list_roofs(
        None, city="Paris", page=(50, 200), min_score=None, include_geometry=False
    )

    assert calls == [("London", None, (50, 0), True), ("Paris", None, (50, 200), False)]
    assert [summary.roof_id for summary in london] == [roof.roof.id]
    assert paris == []


def test_summary_carries_city_and_roof_class(roof: RoofWithLocation) -> None:
    summary = roof_service.to_summary(roof)

    assert (summary.city, summary.roof_class) == ("Athens", "small")


def test_detail_carries_city_and_roof_class(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation
) -> None:
    monkeypatch.setattr("app.repositories.roofs.get_roof", lambda _db, _roof_id: roof)
    monkeypatch.setattr("app.repositories.measurements.list_for_roof", lambda _db, _roof_id: [])

    detail = roof_service.get_roof_detail(MagicMock(), roof.roof.id)

    assert (detail.city, detail.roof_class) == ("Athens", "small")


def test_summary_estimates_cost_from_area(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation
) -> None:
    monkeypatch.setattr(roof_service, "COST_PER_M2_EUR", 12.0)

    assert roof_service.to_summary(roof).estimated_cost_eur == 850.0 * 12.0


def test_summary_rejects_unknown_roof_class(roof: RoofWithLocation) -> None:
    roof.roof.roof_class = "medium"

    with pytest.raises(ValidationError):
        roof_service.to_summary(roof)


def test_summary_carries_the_footprint_as_geojson(roof: RoofWithLocation) -> None:
    geometry = roof_service.to_summary(roof).geometry

    assert geometry.type == "Polygon"
    assert geometry.coordinates[0][0] == [23.73, 37.98]


def test_detail_requires_a_footprint(
    monkeypatch: pytest.MonkeyPatch, roof: RoofWithLocation
) -> None:
    without_geometry = RoofWithLocation(roof=roof.roof, lat=roof.lat, lon=roof.lon)
    monkeypatch.setattr("app.repositories.roofs.get_roof", lambda _db, _rid: without_geometry)
    monkeypatch.setattr("app.repositories.measurements.list_for_roof", lambda _db, _rid: [])

    with pytest.raises(ValidationError):
        roof_service.get_roof_detail(MagicMock(), roof.roof.id)
