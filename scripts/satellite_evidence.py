"""CoolRoof Commons - REAL evidence: measured surface temperatures of dark vs bright roofs.

Source 1 (measured): satellite land surface temperature reduced per roof by
scripts/fetch_satellite.py. Nothing here is simulated.

Each case is one roof set (small residential / large industrial) seen by one thermal
instrument (Landsat / ECOSTRESS). Cases differ in how much of a thermal pixel a roof
fills, which is the question this file answers: does the dark-vs-bright signal grow as
the roof-to-pixel area ratio grows?

These are observational comparisons of different buildings, NOT a controlled experiment:
area, height, construction, shading and location also differ between the groups, so any
temperature gap is an association with albedo, not the measured effect of a coating.
The statistics live in ml/evidence_stats.py and are applied identically to every case;
this script only prepares the data and describes the results. Because every case is a
separate test, the p-values are corrected for multiple comparisons before anything is
called significant, and the large sets are analysed after scripts/clean_large_roofs.py
removed stadiums, sports halls and garages (the uncleaned result is kept alongside).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shapely.geometry import shape  # noqa: E402

from cities import (  # noqa: E402
    CITIES,
    LARGE_ROOF_EXCLUSIONS_PATH,
    City,
    buildings_path,
    metrics_path,
)
from evidence_conclusion import build_conclusion  # noqa: E402
from fetch_satellite import INSTRUMENTS, PRIMARY_INSTRUMENT, ROOF_SETS  # noqa: E402
from ml.evidence_stats import RoofSample, compare_albedo_groups  # noqa: E402
from multiple_comparisons import (  # noqa: E402
    benjamini_hochberg_adjusted,
    bonferroni_adjusted,
    bonferroni_alpha,
)

OUTPUT_PATH = REPO_ROOT / "data" / "satellite_evidence.json"
MEASURED = "measured"
LARGE = "large"
STATISTIC = "per-roof zonal mean of the cloud-masked seasonal median LST, deg C"
CAVEAT = (
    "Observational comparison between different buildings, not a controlled "
    "before/after experiment."
)
MULTIPLE_COMPARISON_NOTE = (
    "Each case is a separate t-test, so with {n} tests at alpha {alpha} about "
    "{expected:.1f} raw 'significant' result is expected by chance alone; only results that "
    "survive Bonferroni or Benjamini-Hochberg correction count as findings."
)
# Below this share of a pixel the roof is a minority of what the sensor sees.
FAR_SMALLER_RATIO = 0.5
FULL_PIXEL_RATIO = 1.0
RATIO_DECIMALS = 3
HEADLINE_CASE_ID = "athens_small_roofs"
SIGNIFICANCE_FLAGS = ("significant_raw", "significant_bonferroni", "significant_fdr")

ExcludedIds = Mapping[str, frozenset[str]]


def case_id(city: City, roof_set: str, instrument_key: str) -> str:
    """The primary-instrument cases keep their original ids (athens_small_roofs)."""
    suffix = "" if instrument_key == PRIMARY_INSTRUMENT else f"_{instrument_key}"
    return f"{city.key}_{roof_set}_roofs{suffix}"


def load_exclusions(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/clean_large_roofs.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def excluded_ids(exclusions: dict) -> dict[str, frozenset[str]]:
    return {
        city_key: frozenset(item["roof_id"] for item in result["excluded"])
        for city_key, result in exclusions["cities"].items()
    }


def load_centroids(path: Path) -> dict[str, tuple[float, float]]:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    centroids = {}
    for feature in features:
        centroid = shape(feature["geometry"]).centroid
        centroids[feature["properties"]["roof_id"]] = (centroid.y, centroid.x)
    return centroids


def load_samples(
    city: City, roof_set: str, instrument_name: str, excluded: frozenset[str]
) -> list[RoofSample]:
    """Roofs without a satellite value are skipped rather than filled in."""
    path = metrics_path(city, roof_set)
    if not path.exists():
        return []
    centroids = load_centroids(buildings_path(city, roof_set))
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["instrument"] == instrument_name
            and row["albedo"]
            and row["surface_temp_c"]
            and row["roof_id"] not in excluded
        ]
    return [
        RoofSample(
            roof_id=row["roof_id"],
            albedo=float(row["albedo"]),
            surface_temp_c=float(row["surface_temp_c"]),
            area_m2=float(row["area_m2"]),
            lat=centroids[row["roof_id"]][0],
            lon=centroids[row["roof_id"]][1],
        )
        for row in rows
    ]


def footprint_text(ratio: float, resolution_m: int) -> str:
    if ratio < FAR_SMALLER_RATIO:
        return (
            "Roof is far smaller than one thermal pixel, so the measurement describes the "
            "surroundings, not the roof."
        )
    if ratio < FULL_PIXEL_RATIO:
        return (
            f"Roof fills about {ratio:.0%} of one {resolution_m} m thermal pixel, so the "
            "measurement mixes the roof with its surroundings."
        )
    return f"Roof spans about {ratio:.1f} thermal pixels and dominates what is measured."


def interpret(case: dict) -> str:
    """Raw significance alone is never reported as a finding: it must survive correction."""
    footprint = footprint_text(case["roof_to_pixel_area_ratio"], case["instrument_resolution_m"])
    if case["delta_c"] < 0:
        direction = "cooler (association, not causation)"
    else:
        direction = "warmer, contrary to expectation"
    if case["significant_bonferroni"] or case["significant_fdr"]:
        return f"{footprint} Bright roofs are significantly {direction} after correction."
    if case["significant_raw"]:
        return (
            f"{footprint} Bright roofs are {direction} at raw p < 0.05, but this does not "
            "survive multiple-comparison correction, so it is not a finding."
        )
    return f"{footprint} No significant difference between bright and dark roofs."


def resolution_caveat(
    instrument_name: str, resolution_m: int, mean_area: float, ratio: float
) -> str:
    return (
        f"{instrument_name} resolves surface temperature at {resolution_m} m, i.e. "
        f"{resolution_m**2:,} m2 per pixel; the mean roof here is {mean_area:,.0f} m2, "
        f"{ratio:.1%} of one pixel, so neighbouring surfaces contribute the remaining "
        f"{max(0.0, 1 - ratio):.0%} of each measured value."
    )


def build_case(city: City, roof_set: str, instrument_key: str, samples: list[RoofSample]) -> dict:
    instrument = INSTRUMENTS[instrument_key]
    pixel_area_m2 = instrument.resolution_m**2
    mean_area = sum(sample.area_m2 for sample in samples) / len(samples)
    ratio = mean_area / pixel_area_m2
    result = compare_albedo_groups(samples)
    return {
        "case_id": case_id(city, roof_set, instrument_key),
        "city": city.name,
        "period": f"{city.summer[0]}..{city.summer[1]}",
        "roof_class": roof_set,
        "instrument": instrument.name,
        "instrument_resolution_m": instrument.resolution_m,
        "pixel_area_m2": pixel_area_m2,
        "mean_roof_area_m2": round(mean_area, 1),
        "roof_to_pixel_area_ratio": round(ratio, RATIO_DECIMALS),
        "n_low": result["low_albedo_group"]["n"],
        "n_high": result["high_albedo_group"]["n"],
        **result,
        "resolution_caveat": resolution_caveat(
            instrument.name, instrument.resolution_m, mean_area, ratio
        ),
    }


def family_alpha(cases: Sequence[dict]) -> float:
    """Every case is tested by ml/evidence_stats.py at the same level; mixing levels in
    one correction family would make the corrected thresholds meaningless."""
    levels = {case["significance_level"] for case in cases}
    if len(levels) != 1:
        raise SystemExit(f"Cases use different significance levels: {sorted(levels)}.")
    return levels.pop()


def apply_corrections(cases: Sequence[dict]) -> list[dict]:
    alpha = family_alpha(cases)
    p_values = [case["p_value"] for case in cases]
    bonferroni = bonferroni_adjusted(p_values)
    fdr = benjamini_hochberg_adjusted(p_values)
    corrected = []
    for case, p_bonferroni, q_value in zip(cases, bonferroni, fdr):
        flagged = {
            **case,
            "significant_raw": case["p_value"] < alpha,
            "significant_bonferroni": case["p_value"] < bonferroni_alpha(alpha, len(cases)),
            "significant_fdr": q_value <= alpha,
            "p_value_bonferroni": p_bonferroni,
            "q_value_fdr": q_value,
        }
        corrected.append({**flagged, "interpretation": interpret(flagged)})
    return corrected


def city_cases(city: City, excluded: frozenset[str]) -> list[dict]:
    cases = []
    for roof_set in ROOF_SETS:
        roof_excluded = excluded if roof_set == LARGE else frozenset()
        for instrument_key, instrument in INSTRUMENTS.items():
            samples = load_samples(city, roof_set, instrument.name, roof_excluded)
            if samples:
                cases.append(build_case(city, roof_set, instrument_key, samples))
    return cases


def analyse(excluded: ExcludedIds) -> list[dict]:
    cases = [
        case
        for city in CITIES.values()
        for case in city_cases(city, excluded.get(city.key, frozenset()))
    ]
    if not cases:
        raise SystemExit("No satellite metrics found. Run scripts/fetch_satellite.py first.")
    return apply_corrections(cases)


def headline_fields(cases: Sequence[dict]) -> dict:
    """The contract's single-case fields carry the headline case, the original Athens
    small-roof comparison when present; every case stays available under "cases"."""
    headline = next((c for c in cases if c["case_id"] == HEADLINE_CASE_ID), cases[0])
    keys = (
        "case_id",
        "instrument",
        "instrument_resolution_m",
        "low_albedo_group",
        "high_albedo_group",
        "delta_c",
        "p_value",
        "significant",
        "resolution_caveat",
    )
    return {key: headline[key] for key in keys}



def cleaning_block(exclusions: dict, cleaned: Sequence[dict], uncleaned: Sequence[dict]) -> dict:
    """The uncleaned cases are kept for every roof set that lost roofs, so the effect of
    the cleaning stays visible instead of silently replacing the earlier numbers."""
    affected = {
        CITIES[key].name for key, result in exclusions["cities"].items() if result["n_excluded"]
    }
    before = [c for c in uncleaned if c["roof_class"] == LARGE and c["city"] in affected]
    after = {case["case_id"]: case for case in cleaned}
    changed = [
        case["case_id"]
        for case in before
        if any(case[flag] != after[case["case_id"]][flag] for flag in SIGNIFICANCE_FLAGS)
    ]
    return {
        "rule": exclusions["rule"],
        "cities": exclusions["cities"],
        "significance_changed": bool(changed),
        "changed_case_ids": changed,
        "cases_before_cleaning": before,
    }


def build_evidence(exclusions: dict) -> dict:
    cases = analyse(excluded_ids(exclusions))
    uncleaned = analyse({})
    alpha = family_alpha(cases)
    periods = sorted({f"{case['city']} {case['period']}" for case in cases})
    return {
        "source": MEASURED,
        "data_source": MEASURED,
        "period": "; ".join(periods),
        "statistic": STATISTIC,
        **headline_fields(cases),
        "n_tests": len(cases),
        "bonferroni_alpha": bonferroni_alpha(alpha, len(cases)),
        "multiple_comparison_note": MULTIPLE_COMPARISON_NOTE.format(
            n=len(cases), alpha=alpha, expected=alpha * len(cases)
        ),
        "cases": cases,
        "large_roof_cleaning": cleaning_block(exclusions, cases, uncleaned),
        "conclusion": build_conclusion(cases, alpha),
        "caveat": CAVEAT,
    }


def _case_line(case: dict) -> str:
    flags = " ".join(f"{flag.split('_')[1]}={case[flag]}" for flag in SIGNIFICANCE_FLAGS)
    return (
        f"{case['case_id']} (roof/pixel {case['roof_to_pixel_area_ratio']}, "
        f"n={case['n_low']}+{case['n_high']}): delta {case['delta_c']} C, "
        f"p={case['p_value']:.3g}, {flags}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare measured LST of dark vs bright roofs.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--exclusions", type=Path, default=LARGE_ROOF_EXCLUSIONS_PATH)
    args = parser.parse_args()
    evidence = build_evidence(load_exclusions(args.exclusions))
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"{evidence['n_tests']} tests, Bonferroni alpha {evidence['bonferroni_alpha']:.5f}")
    for case in evidence["cases"]:
        print(_case_line(case))
    print("Before cleaning:")
    for case in evidence["large_roof_cleaning"]["cases_before_cleaning"]:
        print(_case_line(case))
    print(evidence["conclusion"]["text"])
    print(f"Written to {args.output}.")


if __name__ == "__main__":
    main()
