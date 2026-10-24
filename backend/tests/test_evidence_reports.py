import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.exceptions import ArtifactNotGeneratedError
from app.services import evidence_reports

GROUP = {
    "n": 75,
    "albedo_range": [0.17, 0.25],
    "mean_c": 41.7,
    "median_c": 41.6,
    "std_c": 1.2,
    "mean_area_m2": 180.0,
    "centroid": [37.956, 23.758],
}
CASE = {
    "case_id": "athens_small_roofs",
    "roof_class": "small",
    "instrument": "Landsat 8/9 C2L2 ST_B10",
    "instrument_resolution_m": 100,
    "mean_roof_area_m2": 180.0,
    "roof_to_pixel_area_ratio": 0.018,
    "n_low": 79,
    "n_high": 75,
    "low_albedo_group": GROUP,
    "high_albedo_group": {**GROUP, "albedo_range": [0.31, 0.45], "mean_c": 41.4},
    "delta_c": -0.21,
    "p_value": 0.25,
    "significant": False,
    "significant_raw": False,
    "significant_bonferroni": False,
    "significant_fdr": False,
    "interpretation": "Roof is far smaller than one thermal pixel.",
    "resolution_caveat": "Landsat resolves 100 m; the roof is 1.8% of a pixel.",
}
SATELLITE = {
    "source": "measured",
    "data_source": "measured",
    "period": "2026-06-01..2026-08-31",
    **{
        key: CASE[key]
        for key in (
            "instrument",
            "instrument_resolution_m",
            "low_albedo_group",
            "high_albedo_group",
            "delta_c",
            "p_value",
            "significant",
            "resolution_caveat",
        )
    },
    "n_tests": 2,
    "bonferroni_alpha": 0.025,
    "multiple_comparison_note": "Each case is a separate t-test.",
    "cases": [CASE, {**CASE, "case_id": "athens_large_roofs", "roof_class": "large"}],
    "conclusion": {
        "n_cases_tested": 2,
        "n_significant_raw": 0,
        "n_significant_bonferroni": 0,
        "n_significant_fdr": 0,
        "surviving_case_ids": [],
        "untested_explanations": ["Emissivity."],
        "verdict": "Satellite data is not sufficient for roof-level verification.",
        "text": "2 cases were tested; 0 of them reached raw p < 0.05.",
    },
    "caveat": "Observational comparison between different buildings.",
}
METRICS = {
    "data_source": "simulated",
    "generated_at": "2026-10-21T12:00:00+00:00",
    "anomaly_detection": {"rules": {"recall": 0.79}},
    "normalization": {"raw_delta": {"range_c": 19.1}},
}


@pytest.fixture
def artifact_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(evidence_reports, "METRICS_PATH", tmp_path / "metrics.json")
    monkeypatch.setattr(evidence_reports, "SATELLITE_EVIDENCE_PATH", tmp_path / "sat.json")
    monkeypatch.setattr(evidence_reports, "CLIMATE_COMPARISON_PATH", tmp_path / "climate.json")
    monkeypatch.setattr(evidence_reports, "SNAPSHOT_DIR", tmp_path / "snapshots")
    return tmp_path


def test_missing_artifact_falls_back_to_snapshot(artifact_dir: Path) -> None:
    (artifact_dir / "snapshots").mkdir()
    (artifact_dir / "snapshots" / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")

    assert evidence_reports.get_metrics().data_source == "simulated"


def test_fresh_artifact_wins_over_snapshot(artifact_dir: Path) -> None:
    (artifact_dir / "snapshots").mkdir()
    stale = {**METRICS, "generated_at": "2000-01-01T00:00:00+00:00"}
    (artifact_dir / "snapshots" / "metrics.json").write_text(json.dumps(stale), encoding="utf-8")
    (artifact_dir / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")

    assert evidence_reports.get_metrics().generated_at == METRICS["generated_at"]


def test_mislabelled_snapshot_is_rejected(artifact_dir: Path) -> None:
    (artifact_dir / "snapshots").mkdir()
    mislabelled = {**SATELLITE, "data_source": "simulated"}
    (artifact_dir / "snapshots" / "sat.json").write_text(json.dumps(mislabelled), encoding="utf-8")

    with pytest.raises(ValidationError):
        evidence_reports.get_satellite_evidence()


def test_satellite_evidence_is_measured(artifact_dir: Path) -> None:
    (artifact_dir / "sat.json").write_text(json.dumps(SATELLITE), encoding="utf-8")

    evidence = evidence_reports.get_satellite_evidence()

    assert evidence.data_source == "measured"
    assert [case.case_id for case in evidence.cases] == ["athens_small_roofs", "athens_large_roofs"]
    assert evidence.cases[0].significant is False
    assert evidence.instrument_resolution_m == 100
    assert "pixel" in evidence.resolution_caveat
    assert evidence.conclusion.n_significant_bonferroni == 0


def test_evidence_without_correction_flags_is_rejected(artifact_dir: Path) -> None:
    uncorrected = {key: value for key, value in CASE.items() if key != "significant_fdr"}
    (artifact_dir / "sat.json").write_text(
        json.dumps({**SATELLITE, "cases": [uncorrected]}), encoding="utf-8"
    )

    with pytest.raises(ValidationError):
        evidence_reports.get_satellite_evidence()


def test_metrics_are_simulated(artifact_dir: Path) -> None:
    (artifact_dir / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")

    assert evidence_reports.get_metrics().data_source == "simulated"


def test_mislabelled_artifact_is_rejected(artifact_dir: Path) -> None:
    mislabelled = {**SATELLITE, "data_source": "simulated"}
    (artifact_dir / "sat.json").write_text(json.dumps(mislabelled), encoding="utf-8")

    with pytest.raises(ValidationError):
        evidence_reports.get_satellite_evidence()


def test_missing_artifact_names_the_script(artifact_dir: Path) -> None:
    with pytest.raises(ArtifactNotGeneratedError, match="scripts/metrics.py"):
        evidence_reports.get_metrics()


def test_evidence_without_cases_is_rejected(artifact_dir: Path) -> None:
    (artifact_dir / "sat.json").write_text(json.dumps({**SATELLITE, "cases": []}), encoding="utf-8")

    with pytest.raises(ValidationError):
        evidence_reports.get_satellite_evidence()


BALANCE = {
    "cooling_benefit_kwh_per_m2": 180.1,
    "heating_penalty_kwh_per_m2": 65.0,
    "net_benefit_kwh_per_m2": 115.0,
    "penalty_to_benefit_ratio": 0.361,
}
CLIMATE = {
    "data_source": "simulated",
    "primary_method": "demand_weighted",
    "secondary_method": "solar_only",
    "secondary_method_note": "solar_only charges every winter sun hour as a penalty.",
    "conclusion": "London's heating need is 2.1x Athens's.",
    "assumptions": ["Interior share depends on insulation."],
    "method": "kept-out sunlight in demand hours",
    "caveat": "Rough estimate; depends on insulation.",
    "cities": [
        {
            "city": "London",
            "summer_surface_cooling_c": 16.5,
            "heating_degree_hours": 19188.0,
            "cooling_degree_hours": 2042.0,
            "net_benefit_kwh_per_m2": 115.0,
            "heat_reference": {"summer_max_ambient_c": 36.0, "summer_year": 2026},
            "demand_weighted": BALANCE,
            "solar_only": {**BALANCE, "net_benefit_kwh_per_m2": 292.4},
        }
    ],
}


def test_climate_comparison_is_simulated(artifact_dir: Path) -> None:
    (artifact_dir / "climate.json").write_text(json.dumps(CLIMATE), encoding="utf-8")

    report = evidence_reports.get_climate_comparison()

    assert report.data_source == "simulated"
    assert report.primary_method == "demand_weighted"
    london = report.cities[0]
    assert london.city == "London"
    assert london.net_benefit_kwh_per_m2 == london.demand_weighted.net_benefit_kwh_per_m2


def test_climate_comparison_without_primary_method_is_rejected(artifact_dir: Path) -> None:
    unmarked = {key: value for key, value in CLIMATE.items() if key != "primary_method"}
    (artifact_dir / "climate.json").write_text(json.dumps(unmarked), encoding="utf-8")

    with pytest.raises(ValidationError):
        evidence_reports.get_climate_comparison()


def test_missing_climate_comparison_names_the_script(artifact_dir: Path) -> None:
    with pytest.raises(ArtifactNotGeneratedError, match="climate_comparison.py"):
        evidence_reports.get_climate_comparison()
