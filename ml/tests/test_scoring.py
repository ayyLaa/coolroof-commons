import pytest

from ml.scoring import (
    NEUTRAL_NORMALIZED_VALUE,
    InvalidSelectionInputError,
    RoofMetrics,
    ScoredRoof,
    compute_priority_scores,
    normalize_min_max,
    select_roofs,
    total_benefit,
)


@pytest.fixture
def roof_metrics() -> list[RoofMetrics]:
    return [
        RoofMetrics(roof_id="ATH-1000", area_m2=1000.0, albedo=0.10, surface_temp_c=62.0),
        RoofMetrics(roof_id="ATH-1001", area_m2=100.0, albedo=0.60, surface_temp_c=40.0),
        RoofMetrics(roof_id="ATH-1002", area_m2=550.0, albedo=0.35, surface_temp_c=51.0),
    ]


def test_normalize_min_max_maps_to_unit_range() -> None:
    assert normalize_min_max([10.0, 20.0, 15.0]) == [0.0, 1.0, 0.5]


def test_normalize_min_max_constant_values_are_neutral() -> None:
    assert normalize_min_max([3.0, 3.0]) == [NEUTRAL_NORMALIZED_VALUE] * 2


def test_hot_dark_large_roof_scores_highest(roof_metrics: list[RoofMetrics]) -> None:
    scores = {roof.roof_id: roof.priority_score for roof in compute_priority_scores(roof_metrics)}

    assert scores["ATH-1000"] == pytest.approx(1.0)
    assert scores["ATH-1001"] == pytest.approx(0.0)
    assert 0.0 < scores["ATH-1002"] < 1.0


def test_compute_priority_scores_empty_input() -> None:
    assert compute_priority_scores([]) == []


def test_select_roofs_respects_budget() -> None:
    roofs = [
        ScoredRoof(roof_id="ATH-1000", area_m2=100.0, priority_score=0.9),
        ScoredRoof(roof_id="ATH-1001", area_m2=100.0, priority_score=0.8),
        ScoredRoof(roof_id="ATH-1002", area_m2=100.0, priority_score=0.1),
    ]

    selected = select_roofs(roofs, budget_eur=2000.0, cost_per_m2=10.0)

    assert [roof.roof_id for roof in selected] == ["ATH-1000", "ATH-1001"]


def test_select_roofs_prefers_single_roof_when_greedy_is_worse() -> None:
    roofs = [
        ScoredRoof(roof_id="ATH-1000", area_m2=1.0, priority_score=0.02),
        ScoredRoof(roof_id="ATH-1001", area_m2=100.0, priority_score=1.0),
    ]

    selected = select_roofs(roofs, budget_eur=1000.0, cost_per_m2=10.0)

    assert [roof.roof_id for roof in selected] == ["ATH-1001"]
    assert total_benefit(selected) == pytest.approx(1.0)


def test_select_roofs_returns_empty_when_nothing_affordable() -> None:
    roofs = [ScoredRoof(roof_id="ATH-1000", area_m2=500.0, priority_score=1.0)]

    assert select_roofs(roofs, budget_eur=100.0, cost_per_m2=10.0) == []


@pytest.mark.parametrize(("budget_eur", "cost_per_m2"), [(-1.0, 10.0), (1000.0, 0.0)])
def test_select_roofs_rejects_invalid_input(budget_eur: float, cost_per_m2: float) -> None:
    with pytest.raises(InvalidSelectionInputError):
        select_roofs([], budget_eur=budget_eur, cost_per_m2=cost_per_m2)
