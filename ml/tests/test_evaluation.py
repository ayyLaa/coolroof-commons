import random
from datetime import datetime

import pytest

from ml.anomaly import default_outlier_model
from ml.conditions import Weather
from ml.evaluation import (
    INJECTORS,
    REPLAY_KIND,
    LabelledSession,
    build_labelled_sessions,
    confusion_metrics,
    evaluate_anomaly_detection,
    normalization_stability,
)
from ml.synthetic_series import generate_measurement_sessions

BEFORE = (datetime(2026, 6, 1, 13), Weather(31.0, 820.0, 3.0))
VARIED_AFTER_WEATHER = [
    (datetime(2026, 7, 1, 10), Weather(28.0, 450.0, 4.0)),
    (datetime(2026, 7, 2, 13), Weather(34.0, 880.0, 1.5)),
    (datetime(2026, 7, 3, 15), Weather(36.0, 700.0, 6.0)),
    (datetime(2026, 7, 4, 11), Weather(31.0, 300.0, 3.0)),
]


def test_confusion_metrics() -> None:
    metrics = confusion_metrics([True, True, False, False], [True, False, True, False])

    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5


def test_confusion_metrics_without_predictions() -> None:
    assert confusion_metrics([False, False], [True, False])["precision"] == 0.0


def test_injected_sessions_are_labelled_and_only_replay_keeps_device() -> None:
    honest = generate_measurement_sessions(count=30, seed=1)

    labelled = build_labelled_sessions(honest, random.Random(1))

    kinds = {item.kind for item in labelled if item.is_anomaly}
    assert kinds == set(INJECTORS)
    for item in labelled:
        if item.is_anomaly and item.kind != REPLAY_KIND:
            assert item.session.device_id != honest[0].device_id


def test_layers_complement_each_other() -> None:
    report = evaluate_anomaly_detection()
    rates = report["detection_rate_by_kind"]

    assert report["data_source"] == "simulated"
    assert rates["replayed_upload"]["rules"] == 1.0
    assert rates["implausible_cooling"]["rules"] == 0.0
    assert rates["implausible_cooling"]["isolation_forest"] > 0.8
    assert report["combined"]["recall"] > report["rules"]["recall"]


def test_seed_sessions_are_included() -> None:
    seed = generate_measurement_sessions(count=1, seed=99)[0]

    report = evaluate_anomaly_detection([LabelledSession(seed, False, "seed_normal")])

    assert report["detection_rate_by_kind"]["seed_normal"]["n"] == 1


def test_normalization_keeps_delta_stable() -> None:
    result = normalization_stability(BEFORE, VARIED_AFTER_WEATHER, 0.12, 0.75)

    assert result["data_source"] == "simulated"
    assert result["normalized_delta"]["std_c"] < result["raw_delta"]["std_c"] / 3
    assert result["normalized_delta"]["mean_c"] == pytest.approx(
        result["true_delta_at_standard_c"], abs=3.0
    )


def test_normalization_needs_scenarios() -> None:
    with pytest.raises(ValueError):
        normalization_stability(BEFORE, [], 0.12, 0.75)


@pytest.fixture(autouse=True, scope="module")
def warm_outlier_model() -> None:
    default_outlier_model()
