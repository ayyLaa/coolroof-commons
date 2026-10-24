import pytest

from ml.evidence_stats import (
    InsufficientSampleError,
    RoofSample,
    compare_albedo_groups,
    split_by_albedo_quartile,
)

ATHENS = (37.97, 23.75)


def sample(index: int, albedo: float, temp_c: float) -> RoofSample:
    return RoofSample(
        roof_id=f"ATH-{1000 + index}",
        albedo=albedo,
        surface_temp_c=temp_c,
        area_m2=200.0 + index,
        lat=ATHENS[0] + index * 1e-4,
        lon=ATHENS[1],
    )


@pytest.fixture
def bright_roofs_are_cooler() -> list[RoofSample]:
    """Albedo 0.10..0.49 with temperature falling 0.1 C per albedo step, plus wobble."""
    return [
        sample(i, 0.10 + i * 0.01, 45.0 - i * 0.1 + (0.3 if i % 2 else -0.3)) for i in range(40)
    ]


def test_quartile_split_takes_both_tails(bright_roofs_are_cooler: list[RoofSample]) -> None:
    low, high = split_by_albedo_quartile(bright_roofs_are_cooler)

    assert len(low) == len(high) == 10
    assert max(s.albedo for s in low) < min(s.albedo for s in high)


def test_bright_group_is_cooler_and_significant(bright_roofs_are_cooler: list[RoofSample]) -> None:
    result = compare_albedo_groups(bright_roofs_are_cooler)

    assert result["delta_c"] < 0
    assert result["p_value"] < 0.001
    assert result["significant"] is True
    assert result["low_albedo_group"]["n"] == 10
    assert result["confounders"]["area_difference_m2"] > 0
    assert "association" in result["confounders"]["note"]


def test_no_albedo_effect_is_not_significant() -> None:
    flat = [sample(i, 0.10 + i * 0.01, 42.0 + (0.5 if i % 2 else -0.5)) for i in range(40)]

    result = compare_albedo_groups(flat)

    assert result["p_value"] > 0.05
    assert result["significant"] is False


def test_too_few_roofs_raise() -> None:
    with pytest.raises(InsufficientSampleError):
        compare_albedo_groups([sample(i, 0.1 * i, 40.0) for i in range(3)])
