import pytest

from app.core.config import thresholds_for

CONFIG = {
    "default": {
        "min_normalized_delta_c": -8.0,
        "min_coverage_pct": 85,
        "force_majeure_gust_ms": 20.0,
        "force_majeure_precip_mm": 50.0,
        "durability_check_days": 180,
        "winter_penalty_check": False,
    },
    "by_city": {
        "athens": {"min_normalized_delta_c": -8.0},
        "london": {
            "min_normalized_delta_c": -6.0,
            "winter_penalty_check": True,
            "rationale": "Scaled from Athens by summer sun.",
        },
    },
}


def test_city_override_is_merged_over_defaults() -> None:
    london = thresholds_for("London", CONFIG)

    assert london.min_normalized_delta_c == -6.0
    assert london.winter_penalty_check is True
    assert london.min_coverage_pct == 85
    assert london.rationale == "Scaled from Athens by summer sun."


@pytest.mark.parametrize("city", [None, "Lisbon", ""])
def test_unknown_city_falls_back_to_default(city: str | None) -> None:
    thresholds = thresholds_for(city, CONFIG)

    assert thresholds.min_normalized_delta_c == -8.0
    assert thresholds.winter_penalty_check is False
    assert thresholds.rationale is None


def test_repository_thresholds_file_is_city_based() -> None:
    assert thresholds_for("London").min_normalized_delta_c == -6.0
    assert thresholds_for("Athens").min_normalized_delta_c == -8.0


@pytest.mark.parametrize("city", ["Athens", "London"])
def test_every_pilot_city_states_why_its_threshold_has_its_value(city: str) -> None:
    rationale = thresholds_for(city).rationale

    assert rationale is not None
    assert f"{thresholds_for(city).min_normalized_delta_c:.1f}" in rationale
    assert "calibrated with local measurements" in rationale
