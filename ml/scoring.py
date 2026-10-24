"""Roof prioritisation and budget-constrained selection.

Pure functions only: callers pass plain roof metrics in and get scores back, so the
module can be tested and reused without a database, HTTP layer or Earth Engine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Surface temperature is weighted highest because it is the direct heat signal the
# programme pays to reduce and the quantity verification later measures.
WEIGHT_SURFACE_TEMP = 0.45
# Low albedo marks how much a reflective coating can still improve; it is the
# intervention's physical lever, so it is weighted just below temperature.
WEIGHT_LOW_ALBEDO = 0.35
# Larger roofs cool more of the neighbourhood per mobilisation, but size alone does
# not make a roof hot, so area gets the smallest share.
WEIGHT_AREA = 0.20
# A metric with identical values across all candidates cannot rank them; every roof
# gets this neutral midpoint so the other components decide.
NEUTRAL_NORMALIZED_VALUE = 0.5


class InvalidSelectionInputError(ValueError):
    """Raised when budget or unit cost would make the selection meaningless."""


@dataclass(frozen=True)
class RoofMetrics:
    roof_id: str
    area_m2: float
    albedo: float
    surface_temp_c: float


@dataclass(frozen=True)
class ScoredRoof:
    roof_id: str
    area_m2: float
    priority_score: float


def normalize_min_max(values: Sequence[float]) -> list[float]:
    """Scores are relative to the candidate set: a roof is urgent compared with its
    neighbours, not against a city-independent absolute scale."""
    low, high = min(values), max(values)
    if high == low:
        return [NEUTRAL_NORMALIZED_VALUE] * len(values)
    return [(value - low) / (high - low) for value in values]


def compute_priority_scores(roofs: Sequence[RoofMetrics]) -> list[ScoredRoof]:
    if not roofs:
        return []
    temp = normalize_min_max([roof.surface_temp_c for roof in roofs])
    albedo = normalize_min_max([roof.albedo for roof in roofs])
    area = normalize_min_max([roof.area_m2 for roof in roofs])
    return [
        ScoredRoof(
            roof_id=roof.roof_id,
            area_m2=roof.area_m2,
            priority_score=(
                WEIGHT_SURFACE_TEMP * temp[i]
                + WEIGHT_LOW_ALBEDO * (1.0 - albedo[i])
                + WEIGHT_AREA * area[i]
            ),
        )
        for i, roof in enumerate(roofs)
    ]


def _validate_selection_input(budget_eur: float, cost_per_m2: float) -> None:
    if budget_eur < 0:
        raise InvalidSelectionInputError(f"budget_eur must be >= 0, got {budget_eur}.")
    if cost_per_m2 <= 0:
        raise InvalidSelectionInputError(f"cost_per_m2 must be > 0, got {cost_per_m2}.")


def _fill_greedily(
    roofs: Sequence[ScoredRoof], budget_eur: float, cost_of: Callable[[ScoredRoof], float]
) -> list[ScoredRoof]:
    ranked = sorted(roofs, key=lambda roof: roof.priority_score / cost_of(roof), reverse=True)
    selected, remaining = [], budget_eur
    for roof in ranked:
        cost = cost_of(roof)
        if cost <= remaining:
            selected.append(roof)
            remaining -= cost
    return selected


def total_benefit(roofs: Sequence[ScoredRoof]) -> float:
    return sum(roof.priority_score for roof in roofs)


def select_roofs(
    roofs: Sequence[ScoredRoof], budget_eur: float, cost_per_m2: float
) -> list[ScoredRoof]:
    """Greedy by benefit per euro, then compared with the best single affordable roof:
    plain ratio-greedy can be arbitrarily bad when one valuable roof is crowded out,
    and this check guarantees at least half of the optimal total benefit."""
    _validate_selection_input(budget_eur, cost_per_m2)

    def cost_of(roof: ScoredRoof) -> float:
        return roof.area_m2 * cost_per_m2

    affordable = [roof for roof in roofs if cost_of(roof) <= budget_eur and roof.area_m2 > 0]
    if not affordable:
        return []
    greedy = _fill_greedily(affordable, budget_eur, cost_of)
    best_single = max(affordable, key=lambda roof: roof.priority_score)
    return greedy if total_benefit(greedy) >= best_single.priority_score else [best_single]
