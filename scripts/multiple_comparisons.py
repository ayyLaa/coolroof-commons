"""Multiple-comparison corrections for the satellite evidence cases.

Running one t-test per case gives each case its own 5% false-positive chance, so across
several cases a single raw p < 0.05 is expected by luck alone. Bonferroni controls the
chance of any false positive (strict); Benjamini-Hochberg controls the expected share of
false positives among the reported ones (less strict). Both are reported side by side.
"""

from __future__ import annotations

from collections.abc import Sequence


def bonferroni_alpha(alpha: float, n_tests: int) -> float:
    return alpha / n_tests


def bonferroni_adjusted(p_values: Sequence[float]) -> list[float]:
    return [min(1.0, p * len(p_values)) for p in p_values]


def benjamini_hochberg_adjusted(p_values: Sequence[float]) -> list[float]:
    """Step-up adjusted p-values (q-values): a case is significant at FDR alpha exactly
    when its q-value is <= alpha, the same decision as the step-up rejection rule."""
    n_tests = len(p_values)
    order = sorted(range(n_tests), key=lambda index: p_values[index], reverse=True)
    adjusted = [1.0] * n_tests
    running_min = 1.0
    for rank_from_top, index in enumerate(order):
        rank = n_tests - rank_from_top
        running_min = min(running_min, p_values[index] * n_tests / rank)
        adjusted[index] = running_min
    return adjusted
