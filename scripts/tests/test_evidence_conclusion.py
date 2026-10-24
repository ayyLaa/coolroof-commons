from evidence_conclusion import ROOF_LEVEL_VERDICT, build_conclusion

ALPHA = 0.05


def case(case_id: str, ratio: float, p_value: float, raw: bool, corrected: bool) -> dict:
    return {
        "case_id": case_id,
        "roof_to_pixel_area_ratio": ratio,
        "p_value": p_value,
        "significant_raw": raw,
        "significant_bonferroni": corrected,
        "significant_fdr": corrected,
    }


def test_raw_hit_lost_after_correction_gives_targeting_verdict() -> None:
    cases = [
        case("athens_small_roofs", 0.017, 0.25, False, False),
        case("london_large_roofs", 0.448, 0.023, True, False),
        case("london_large_roofs_ecostress", 0.915, 0.18, False, False),
    ]

    conclusion = build_conclusion(cases, ALPHA)

    assert conclusion["n_significant_raw"] == 1
    assert conclusion["n_significant_bonferroni"] == conclusion["n_significant_fdr"] == 0
    assert conclusion["surviving_case_ids"] == []
    assert conclusion["verdict"] == ROOF_LEVEL_VERDICT
    assert "did not strengthen" in conclusion["resolution_finding"]
    assert "0.017" in conclusion["text"] and "0.915" in conclusion["text"]


def test_surviving_case_changes_the_verdict() -> None:
    cases = [
        case("athens_small_roofs", 0.017, 0.25, False, False),
        case("london_large_roofs", 0.448, 0.0001, True, True),
    ]

    conclusion = build_conclusion(cases, ALPHA)

    assert conclusion["surviving_case_ids"] == ["london_large_roofs"]
    assert conclusion["verdict"] != ROOF_LEVEL_VERDICT
    assert "did not strengthen" not in conclusion["resolution_finding"]
