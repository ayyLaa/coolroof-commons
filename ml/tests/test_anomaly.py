import random
from datetime import datetime, timedelta

import pytest
from sklearn.ensemble import IsolationForest

from ml.anomaly import (
    AnomalyFlag,
    InsufficientOutlierTrainingDataError,
    assess_measurement,
    build_outlier_training_set,
    default_outlier_model,
    detect_anomalies,
    fit_outlier_model,
)
from ml.conditions import MeasurementSession, Reading, Weather
from ml.synthetic_series import generate_measurement_sessions, simulate_session_readings

START = datetime(2026, 7, 1, 13)
DEVICE_ID = "DEV-0391"
CLEAR_SKY = Weather(ambient_c=34.0, radiation_wm2=850.0, wind_ms=3.0)
OVERCAST = Weather(ambient_c=28.0, radiation_wm2=250.0, wind_ms=3.0)
# Neither low radiation (rule threshold 300) nor an exotic curve, so no rule fires; yet
# 30 C of cooling is far more than 450 W/m2 under strong wind can explain.
IMPLAUSIBLE_FOR_WEATHER = Weather(ambient_c=30.0, radiation_wm2=450.0, wind_ms=6.0)
SEED_LIKE_DELTA_C = -13.0


def readings_from(temps: list[float], step_minutes: int = 1) -> tuple[Reading, ...]:
    return tuple(
        Reading(measured_at=START + timedelta(minutes=i * step_minutes), surface_temp_c=t)
        for i, t in enumerate(temps)
    )


def flags_for(
    readings: tuple[Reading, ...],
    weather: Weather | None = CLEAR_SKY,
    history: list[MeasurementSession] | None = None,
    delta_c: float | None = SEED_LIKE_DELTA_C,
) -> list[AnomalyFlag]:
    return detect_anomalies(readings, weather, history or [], device_id=DEVICE_ID, delta_c=delta_c)


@pytest.fixture
def normal_readings() -> tuple[Reading, ...]:
    return simulate_session_readings(48.6, START, random.Random(1))


@pytest.fixture(scope="module")
def outlier_model() -> IsolationForest:
    return default_outlier_model()


def test_clean_upload_has_no_rule_flags(normal_readings: tuple[Reading, ...]) -> None:
    assert flags_for(normal_readings) == []


def test_repeated_value(normal_readings: tuple[Reading, ...]) -> None:
    frozen = readings_from([45.0, 46.0] + [46.5] * 5 + [47.0] * 9)

    assert AnomalyFlag.REPEATED_VALUE in flags_for(frozen)


def test_four_repeats_are_not_frozen() -> None:
    almost = readings_from([46.5] * 4 + [46.6, 46.7] * 6)

    assert AnomalyFlag.REPEATED_VALUE not in flags_for(almost)


def test_impossible_jump() -> None:
    jumpy = readings_from([45.0 + 0.1 * i for i in range(15)] + [60.0])

    assert AnomalyFlag.IMPOSSIBLE_JUMP in flags_for(jumpy)


def test_shadow_suspect(normal_readings: tuple[Reading, ...]) -> None:
    assert AnomalyFlag.SHADOW_SUSPECT in flags_for(normal_readings, OVERCAST, delta_c=-12.0)


def test_small_delta_under_clouds_is_not_shadow(normal_readings: tuple[Reading, ...]) -> None:
    assert AnomalyFlag.SHADOW_SUSPECT not in flags_for(normal_readings, OVERCAST, delta_c=-4.0)


def test_missing_weather(normal_readings: tuple[Reading, ...]) -> None:
    assert AnomalyFlag.MISSING_WEATHER in flags_for(normal_readings, weather=None)


def test_too_few_readings(normal_readings: tuple[Reading, ...]) -> None:
    assert AnomalyFlag.TOO_FEW_READINGS in flags_for(normal_readings[:9])


def test_timestamp_gap(normal_readings: tuple[Reading, ...]) -> None:
    gappy = readings_from([r.surface_temp_c for r in normal_readings], step_minutes=6)

    assert AnomalyFlag.TIMESTAMP_GAP in flags_for(gappy)


def test_replay_with_fresh_timestamps(normal_readings: tuple[Reading, ...]) -> None:
    earlier = MeasurementSession(DEVICE_ID, normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)
    restamped = tuple(
        Reading(r.measured_at + timedelta(days=30), r.surface_temp_c) for r in normal_readings
    )

    assert AnomalyFlag.REPLAY in flags_for(restamped, history=[earlier])


def test_same_readings_from_other_device_is_not_replay(
    normal_readings: tuple[Reading, ...],
) -> None:
    other = MeasurementSession("DEV-9999", normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)

    assert AnomalyFlag.REPLAY not in flags_for(normal_readings, history=[other])


def test_statistical_outlier_caught_only_by_ml(
    normal_readings: tuple[Reading, ...], outlier_model: IsolationForest
) -> None:
    session = MeasurementSession(DEVICE_ID, normal_readings, IMPLAUSIBLE_FOR_WEATHER, -30.0)

    report = assess_measurement(session, [], outlier_model)

    assert report.rule_flags == ()
    assert report.statistical_flags == (AnomalyFlag.STATISTICAL_OUTLIER,)
    assert report.caught_only_by_statistics
    assert report.outlier_score is not None and report.outlier_score < 0


def test_replay_caught_only_by_rules(
    normal_readings: tuple[Reading, ...], outlier_model: IsolationForest
) -> None:
    session = MeasurementSession(DEVICE_ID, normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)

    report = assess_measurement(session, [session], outlier_model)

    assert report.rule_flags == (AnomalyFlag.REPLAY,)
    assert report.statistical_flags == ()
    assert report.caught_only_by_rules


def test_seed_like_upload_is_normal_for_both_layers(
    normal_readings: tuple[Reading, ...], outlier_model: IsolationForest
) -> None:
    session = MeasurementSession(DEVICE_ID, normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)

    report = assess_measurement(session, [], outlier_model)

    assert report.rule_flags == () and report.statistical_flags == ()


def test_incomplete_upload_is_not_scored(
    normal_readings: tuple[Reading, ...], outlier_model: IsolationForest
) -> None:
    session = MeasurementSession(DEVICE_ID, normal_readings, None, None)

    report = assess_measurement(session, [], outlier_model)

    assert report.rule_flags == (AnomalyFlag.MISSING_WEATHER,)
    assert report.outlier_score is None


def test_training_set_includes_seed_sessions(normal_readings: tuple[Reading, ...]) -> None:
    seed = MeasurementSession(DEVICE_ID, normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)

    samples = build_outlier_training_set([seed])

    assert samples[-1] == seed
    assert len(samples) == len(generate_measurement_sessions()) + 1


def test_fit_rejects_too_few_sessions(normal_readings: tuple[Reading, ...]) -> None:
    seed = MeasurementSession(DEVICE_ID, normal_readings, CLEAR_SKY, SEED_LIKE_DELTA_C)

    with pytest.raises(InsufficientOutlierTrainingDataError):
        fit_outlier_model([seed] * 3)
