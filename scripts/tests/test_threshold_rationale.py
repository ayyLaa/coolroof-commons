import json

import pytest

import threshold_rationale
from threshold_rationale import RationaleError, build_rationale, derived_threshold_c

CONFIG = {
    "default": {"min_normalized_delta_c": -8.0},
    "by_city": {
        "athens": {"min_normalized_delta_c": -8.0},
        "london": {"min_normalized_delta_c": -6.0},
    },
}


def city(name: str, summer_sun: float, median_albedo: float, coated: float = 0.75) -> dict:
    return {
        "city": name,
        "coated_albedo": coated,
        "median_current_albedo": median_albedo,
        "solar_only": {"cooling_benefit_kwh_per_m2": summer_sun * (coated - median_albedo)},
    }


def test_london_is_scaled_from_athens_by_summer_sun() -> None:
    climate = {"cities": [city("Athens", 695.0, 0.279), city("London", 562.0, 0.137)]}

    london = build_rationale(climate, CONFIG)["cities"][1]

    assert london["summer_irradiation"] == pytest.approx(562.0)
    assert london["ratio_to_reference"] == 0.81
    assert london["expected_delta_c"] == pytest.approx(-6.47)
    assert london["derived_threshold_c"] == -6.0
    assert "matches the derived threshold" in london["note"]
    assert "calibrate it with local before/after measurements" in london["note"]


def test_a_chosen_threshold_that_drifts_from_the_derivation_is_flagged() -> None:
    climate = {"cities": [city("Athens", 695.0, 0.279), city("London", 562.0, 0.137)]}
    by_city = {**CONFIG["by_city"], "london": {"min_normalized_delta_c": -7.0}}
    drifted = {**CONFIG, "by_city": by_city}

    london = build_rationale(climate, drifted)["cities"][1]

    assert "differs from the derived -6.0 C" in london["note"]


@pytest.mark.parametrize(("expected", "threshold"), [(-6.47, -6.0), (-8.0, -8.0), (-0.4, 0.0)])
def test_threshold_is_rounded_toward_zero(expected: float, threshold: float) -> None:
    assert derived_threshold_c(expected) == threshold


def test_a_coating_that_does_not_raise_albedo_cannot_be_scaled() -> None:
    climate = {"cities": [city("Athens", 695.0, 0.279), city("London", 562.0, 0.8)]}

    with pytest.raises(RationaleError, match="does not raise albedo"):
        build_rationale(climate, CONFIG)


def test_a_report_without_the_reference_city_is_refused() -> None:
    with pytest.raises(RationaleError, match="athens"):
        build_rationale({"cities": [city("London", 562.0, 0.137)]}, CONFIG)


def test_repository_thresholds_match_the_committed_derivation() -> None:
    """schema/thresholds.json and the committed climate snapshot must not drift apart."""
    snapshot = threshold_rationale.REPO_ROOT / "data" / "snapshots" / "climate_comparison.json"
    climate = json.loads(snapshot.read_text(encoding="utf-8"))
    config = json.loads(threshold_rationale.THRESHOLDS_PATH.read_text(encoding="utf-8"))

    for result in build_rationale(climate, config)["cities"]:
        assert result["derived_threshold_c"] == result["chosen_threshold_c"], result["city"]
