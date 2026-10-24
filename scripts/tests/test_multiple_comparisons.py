import pytest

from multiple_comparisons import (
    benjamini_hochberg_adjusted,
    bonferroni_adjusted,
    bonferroni_alpha,
)

ALPHA = 0.05


def test_single_raw_hit_among_eight_does_not_survive() -> None:
    p_values = [0.25, 0.80, 0.42, 0.89, 0.41, 0.88, 0.0235, 0.18]

    assert bonferroni_alpha(ALPHA, len(p_values)) == pytest.approx(0.00625)
    assert all(p >= bonferroni_alpha(ALPHA, len(p_values)) for p in p_values)
    assert min(benjamini_hochberg_adjusted(p_values)) == pytest.approx(0.188)


def test_benjamini_hochberg_matches_step_up_rule() -> None:
    q_values = benjamini_hochberg_adjusted([0.01, 0.04, 0.03, 0.005])

    assert q_values == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_strong_signals_survive_both_corrections() -> None:
    p_values = [0.0001, 0.0002, 0.6]

    assert [p <= ALPHA for p in bonferroni_adjusted(p_values)] == [True, True, False]
    assert [q <= ALPHA for q in benjamini_hochberg_adjusted(p_values)] == [True, True, False]


def test_adjusted_p_values_are_capped_at_one() -> None:
    assert bonferroni_adjusted([0.5, 0.9]) == [1.0, 1.0]
    assert benjamini_hochberg_adjusted([0.9, 0.95]) == [0.95, 0.95]


def test_zero_tests_raise() -> None:
    with pytest.raises(ZeroDivisionError):
        bonferroni_alpha(ALPHA, 0)
