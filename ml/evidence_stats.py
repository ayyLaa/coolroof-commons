"""Compares measured surface temperatures of dark and bright roofs.

This is an OBSERVATIONAL comparison, not a controlled experiment: the two groups are
different buildings, so area, height, construction, street canyon and location differ
along with albedo. Those confounders are reported next to the result instead of being
corrected for, and the difference must not be read as the causal effect of a coating.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from scipy import stats

LOWER_QUARTILE = 0.25
UPPER_QUARTILE = 0.75
MIN_GROUP_SIZE = 2
SIGNIFICANCE_LEVEL = 0.05
METERS_PER_DEGREE_LATITUDE = 111_320.0
TEMP_DECIMALS = 2
ALBEDO_DECIMALS = 3


class InsufficientSampleError(ValueError):
    """Raised when a group is too small for a t-test."""


@dataclass(frozen=True)
class RoofSample:
    roof_id: str
    albedo: float
    surface_temp_c: float
    area_m2: float
    lat: float
    lon: float


def _quantile(values: Sequence[float], fraction: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[round(fraction * 100) - 1]


def split_by_albedo_quartile(
    samples: Sequence[RoofSample],
) -> tuple[list[RoofSample], list[RoofSample]]:
    albedos = [sample.albedo for sample in samples]
    low_cut, high_cut = _quantile(albedos, LOWER_QUARTILE), _quantile(albedos, UPPER_QUARTILE)
    low = [sample for sample in samples if sample.albedo <= low_cut]
    high = [sample for sample in samples if sample.albedo >= high_cut]
    return low, high


def describe_group(samples: Sequence[RoofSample]) -> dict:
    temps = [sample.surface_temp_c for sample in samples]
    albedos = [sample.albedo for sample in samples]
    return {
        "n": len(samples),
        "albedo_range": [
            round(min(albedos), ALBEDO_DECIMALS),
            round(max(albedos), ALBEDO_DECIMALS),
        ],
        "mean_c": round(statistics.fmean(temps), TEMP_DECIMALS),
        "median_c": round(statistics.median(temps), TEMP_DECIMALS),
        "std_c": round(statistics.stdev(temps), TEMP_DECIMALS),
        "mean_area_m2": round(statistics.fmean(s.area_m2 for s in samples), 1),
        "centroid": [
            round(statistics.fmean(s.lat for s in samples), 5),
            round(statistics.fmean(s.lon for s in samples), 5),
        ],
    }


def centroid_distance_m(first: dict, second: dict) -> float:
    (lat1, lon1), (lat2, lon2) = first["centroid"], second["centroid"]
    dy = (lat2 - lat1) * METERS_PER_DEGREE_LATITUDE
    dx = (lon2 - lon1) * METERS_PER_DEGREE_LATITUDE * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def confounders(low: dict, high: dict) -> dict:
    """Differences besides albedo that could explain part of the temperature gap."""
    return {
        "area_difference_m2": round(high["mean_area_m2"] - low["mean_area_m2"], 1),
        "centroid_distance_m": round(centroid_distance_m(low, high), 1),
        "height": "not available: OSM footprints carry no reliable height for these roofs",
        "note": (
            "Groups are different buildings; area, height, construction, shading and "
            "location are not controlled, so delta_c is an association, not an effect."
        ),
    }


def compare_albedo_groups(samples: Sequence[RoofSample]) -> dict:
    """Welch's t-test (unequal variances): nothing guarantees the two groups have the
    same spread, so the pooled-variance Student test would be the wrong default."""
    low, high = split_by_albedo_quartile(samples)
    if min(len(low), len(high)) < MIN_GROUP_SIZE:
        raise InsufficientSampleError(f"Groups too small for a t-test: {len(low)}, {len(high)}.")
    test = stats.ttest_ind(
        [s.surface_temp_c for s in high], [s.surface_temp_c for s in low], equal_var=False
    )
    low_summary, high_summary = describe_group(low), describe_group(high)
    return {
        "low_albedo_group": low_summary,
        "high_albedo_group": high_summary,
        "delta_c": round(high_summary["mean_c"] - low_summary["mean_c"], TEMP_DECIMALS),
        "t_statistic": round(float(test.statistic), 3),
        "p_value": float(test.pvalue),
        "significant": bool(test.pvalue < SIGNIFICANCE_LEVEL),
        "significance_level": SIGNIFICANCE_LEVEL,
        "test": "Welch two-sample t-test (high vs low albedo)",
        "confounders": confounders(low_summary, high_summary),
    }
