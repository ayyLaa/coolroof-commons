import pytest

from clean_large_roofs import exclusion_reason


@pytest.mark.parametrize(
    ("tags", "reason"),
    [
        ({"building": "stadium"}, "building=stadium"),
        ({"building": "garage"}, "building=garage"),
        ({"building": "yes", "leisure": "sports_centre"}, "leisure=sports_centre"),
        ({"building": "industrial", "amenity": "parking"}, "amenity=parking"),
    ],
)
def test_non_roof_structures_are_excluded(tags: dict, reason: str) -> None:
    assert exclusion_reason(tags, inside_industrial=True) == reason


def test_ordinary_industrial_roofs_are_kept() -> None:
    assert exclusion_reason({"building": "yes"}, inside_industrial=True) is None
    assert exclusion_reason({"building": "warehouse"}, inside_industrial=False) is None
    assert exclusion_reason({"building": "industrial", "amenity": "studio"}, True) is None


def test_generic_building_outside_industrial_area_is_excluded() -> None:
    reason = exclusion_reason({"building": "yes"}, inside_industrial=False)

    assert reason == "building=yes outside landuse=industrial"
