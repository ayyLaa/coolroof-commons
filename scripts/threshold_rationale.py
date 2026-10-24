"""CoolRoof Commons - derives each city's cooling threshold from its summer sunlight.

A coating cools a roof by reflecting sunlight, so the same coating under weaker sun
gives a smaller surface drop. Scaling the reference city's threshold by the ratio of
summer irradiation gives the drop to expect elsewhere; the threshold asks a little less
than that, so a coating doing its job is not failed by the climate.

This is a rough, one-variable derivation (ambient temperature, wind and cloud timing are
ignored). A real programme must calibrate each city's threshold with local before/after
measurements; the note in the output says so for every city.

Reads data/climate_comparison.json (else data/snapshots/) and schema/thresholds.json;
writes data/snapshots/threshold_rationale.json.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIMATE_PATHS = (
    REPO_ROOT / "data" / "climate_comparison.json",
    REPO_ROOT / "data" / "snapshots" / "climate_comparison.json",
)
THRESHOLDS_PATH = REPO_ROOT / "schema" / "thresholds.json"
OUTPUT_PATH = REPO_ROOT / "data" / "snapshots" / "threshold_rationale.json"

# Athens is the city the -8.0 C requirement was set for; others are scaled from it.
REFERENCE_CITY = "athens"
# Thresholds are whole degrees: the derived drop is rounded toward zero to one, so the
# requirement never exceeds the cooling the climate is expected to allow.
THRESHOLD_STEP_C = 1.0
DECIMALS = 2

CAVEAT = (
    "Rough derivation: the threshold scales only with summer irradiation and ignores "
    "ambient temperature, wind, cloud timing and roof build-up. A real programme must "
    "calibrate it with local before/after measurements on coated roofs."
)


class RationaleError(ValueError):
    """The climate report cannot support the derivation."""


def summer_irradiation_kwh_per_m2(city: dict) -> float:
    """Recovered from the solar_only balance, which counts every summer hour:
    benefit = summer irradiation x (coated albedo - current median albedo)."""
    albedo_change = city["coated_albedo"] - city["median_current_albedo"]
    if albedo_change <= 0:
        raise RationaleError(f"{city['city']}: coating does not raise albedo ({albedo_change}).")
    return city["solar_only"]["cooling_benefit_kwh_per_m2"] / albedo_change


def expected_delta_c(reference_threshold_c: float, ratio: float) -> float:
    return reference_threshold_c * ratio


def derived_threshold_c(expected_c: float) -> float:
    """Toward zero: a cooling requirement is negative, and rounding it away from zero
    would ask for more than the expected effect."""
    return math.trunc(expected_c / THRESHOLD_STEP_C) * THRESHOLD_STEP_C


def city_note(name: str, derived_c: float, chosen_c: float, is_reference: bool) -> str:
    if is_reference:
        agreement = f"{name} is the reference city; its threshold is the starting point."
    elif derived_c == chosen_c:
        agreement = f"The chosen {chosen_c:.1f} C matches the derived threshold."
    else:
        agreement = (
            f"The chosen {chosen_c:.1f} C differs from the derived {derived_c:.1f} C; "
            "update schema/thresholds.json or record why."
        )
    return f"{agreement} {CAVEAT}"


def city_rationale(city: dict, reference_sun: float, reference_c: float, chosen: dict) -> dict:
    key = city["city"].lower()
    sun = summer_irradiation_kwh_per_m2(city)
    ratio = sun / reference_sun
    expected = expected_delta_c(reference_c, ratio)
    derived = reference_c if key == REFERENCE_CITY else derived_threshold_c(expected)
    chosen_c = chosen[key]
    return {
        "city": city["city"],
        "summer_irradiation": round(sun, 1),
        "ratio_to_reference": round(ratio, DECIMALS),
        "expected_delta_c": round(expected, DECIMALS),
        "derived_threshold_c": derived,
        "chosen_threshold_c": chosen_c,
        "note": city_note(city["city"], derived, chosen_c, key == REFERENCE_CITY),
    }


def chosen_thresholds(config: dict) -> dict[str, float]:
    default = config["default"]["min_normalized_delta_c"]
    return {
        key: overrides.get("min_normalized_delta_c", default)
        for key, overrides in config["by_city"].items()
    }


def build_rationale(climate: dict, config: dict) -> dict:
    cities = {city["city"].lower(): city for city in climate["cities"]}
    if REFERENCE_CITY not in cities:
        raise RationaleError(f"The climate report has no {REFERENCE_CITY} to scale from.")
    chosen = chosen_thresholds(config)
    reference_c = chosen[REFERENCE_CITY]
    reference_sun = summer_irradiation_kwh_per_m2(cities[REFERENCE_CITY])
    return {
        "reference_city": cities[REFERENCE_CITY]["city"],
        "reference_threshold_c": reference_c,
        "method": (
            "expected drop = reference threshold x (city summer irradiation / reference "
            "summer irradiation); threshold = expected drop rounded toward zero to a whole "
            "degree. Summer irradiation is recovered from the climate comparison's "
            "solar_only cooling benefit."
        ),
        "caveat": CAVEAT,
        "climate_generated_at": climate.get("generated_at"),
        "generated_at": datetime.now(UTC).isoformat(),
        "cities": [
            city_rationale(city, reference_sun, reference_c, chosen) for city in climate["cities"]
        ],
    }


def load_climate() -> dict:
    path = next((p for p in CLIMATE_PATHS if p.exists()), None)
    if path is None:
        raise SystemExit("No climate comparison found. Run scripts/climate_comparison.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    config = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    try:
        rationale = build_rationale(load_climate(), config)
    except RationaleError as error:
        raise SystemExit(str(error)) from error
    OUTPUT_PATH.write_text(json.dumps(rationale, indent=2) + "\n", encoding="utf-8")
    for city in rationale["cities"]:
        print(
            f"{city['city']}: {city['summer_irradiation']} kWh/m2, ratio "
            f"{city['ratio_to_reference']}, expected {city['expected_delta_c']} C, derived "
            f"{city['derived_threshold_c']} C, chosen {city['chosen_threshold_c']} C"
        )
        if city["derived_threshold_c"] != city["chosen_threshold_c"]:
            print(f"  WARNING: {city['note']}", file=sys.stderr)
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
