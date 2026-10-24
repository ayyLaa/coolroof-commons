"""Decides whether a measurement upload can be trusted before it may release funds.

Two independent layers, reported separately on purpose:
- Rules catch failure modes we can name in advance (frozen sensor, replayed upload,
  missing weather). They are explainable but blind to anything not written down.
- An IsolationForest learns what normal uploads look like and flags combinations no
  single rule covers, e.g. a cooling effect too large for the weather it was measured in.
Comparing what each layer catches is the answer to "why is AI needed here".
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from functools import lru_cache

from sklearn.ensemble import IsolationForest

from ml.conditions import MeasurementSession, Reading, Weather
from ml.synthetic_series import generate_measurement_sessions

from ml.config import load_ml_thresholds

_THRESHOLDS = load_ml_thresholds("anomaly")

REPEATED_VALUE_MIN_RUN = _THRESHOLDS["repeated_value_min_run"]
MAX_STEP_JUMP_C = _THRESHOLDS["max_step_jump_c"]
SHADOW_MAX_RADIATION_WM2 = _THRESHOLDS["shadow_max_radiation_wm2"]
SHADOW_MIN_DELTA_C = _THRESHOLDS["shadow_min_delta_c"]
MIN_READING_COUNT = _THRESHOLDS["min_reading_count"]
MAX_READING_GAP = timedelta(minutes=_THRESHOLDS["max_reading_gap_minutes"])

ISOLATION_TREE_COUNT = _THRESHOLDS["isolation_tree_count"]
# Share of the training uploads treated as borderline; the training set is honest data,
# so this only sets how far outside "normal" an upload must fall to be flagged.
OUTLIER_CONTAMINATION = _THRESHOLDS["outlier_contamination"]
OUTLIER_RANDOM_STATE = _THRESHOLDS["outlier_random_state"]
MIN_OUTLIER_TRAINING_SESSIONS = _THRESHOLDS["min_outlier_training_sessions"]
IS_OUTLIER = -1


class AnomalyFlag(str, Enum):
    REPEATED_VALUE = "repeated_value"
    IMPOSSIBLE_JUMP = "impossible_jump"
    SHADOW_SUSPECT = "shadow_suspect"
    MISSING_WEATHER = "missing_weather"
    TOO_FEW_READINGS = "too_few_readings"
    TIMESTAMP_GAP = "timestamp_gap"
    REPLAY = "replay"
    STATISTICAL_OUTLIER = "statistical_outlier"


class InsufficientOutlierTrainingDataError(ValueError):
    """Raised when too few complete sessions exist to learn what normal looks like."""


@dataclass(frozen=True)
class AnomalyReport:
    rule_flags: tuple[AnomalyFlag, ...]
    statistical_flags: tuple[AnomalyFlag, ...]
    outlier_score: float | None

    @property
    def caught_only_by_statistics(self) -> bool:
        return bool(self.statistical_flags) and not self.rule_flags

    @property
    def caught_only_by_rules(self) -> bool:
        return bool(self.rule_flags) and not self.statistical_flags


def _temperatures(readings: Sequence[Reading]) -> list[float]:
    return [reading.surface_temp_c for reading in readings]


def has_repeated_value(readings: Sequence[Reading]) -> bool:
    run, temps = 1, _temperatures(readings)
    for previous, current in zip(temps, temps[1:]):
        run = run + 1 if current == previous else 1
        if run >= REPEATED_VALUE_MIN_RUN:
            return True
    return False


def has_impossible_jump(readings: Sequence[Reading]) -> bool:
    temps = _temperatures(readings)
    steps = (abs(current - previous) for previous, current in zip(temps, temps[1:]))
    return any(step > MAX_STEP_JUMP_C for step in steps)


def is_shadow_suspect(weather: Weather | None, delta_c: float | None) -> bool:
    """Weather comes from a grid model, not the roof: under low radiation a large cooling
    is more likely a probe placed in shade than a working coating."""
    if weather is None or delta_c is None:
        return False
    return weather.radiation_wm2 < SHADOW_MAX_RADIATION_WM2 and delta_c < SHADOW_MIN_DELTA_C


def has_timestamp_gap(readings: Sequence[Reading]) -> bool:
    times = sorted(reading.measured_at for reading in readings)
    return any(current - previous > MAX_READING_GAP for previous, current in zip(times, times[1:]))


def is_replay(
    device_id: str, readings: Sequence[Reading], history: Sequence[MeasurementSession]
) -> bool:
    """Compares temperature sequences only, so re-stamping an old upload with fresh
    timestamps is still recognised as the same data."""
    fingerprint = _temperatures(readings)
    return any(
        past.device_id == device_id and _temperatures(past.readings) == fingerprint
        for past in history
    )


def detect_anomalies(
    readings: Sequence[Reading],
    weather: Weather | None,
    history: Sequence[MeasurementSession],
    *,
    device_id: str,
    delta_c: float | None = None,
) -> list[AnomalyFlag]:
    """weather is the conditions at measurement time (None when unavailable); history
    holds earlier uploads to check for replays."""
    checks = [
        (AnomalyFlag.REPEATED_VALUE, has_repeated_value(readings)),
        (AnomalyFlag.IMPOSSIBLE_JUMP, has_impossible_jump(readings)),
        (AnomalyFlag.SHADOW_SUSPECT, is_shadow_suspect(weather, delta_c)),
        (AnomalyFlag.MISSING_WEATHER, weather is None),
        (AnomalyFlag.TOO_FEW_READINGS, len(readings) < MIN_READING_COUNT),
        (AnomalyFlag.TIMESTAMP_GAP, has_timestamp_gap(readings)),
        (AnomalyFlag.REPLAY, is_replay(device_id, readings, history)),
    ]
    return [flag for flag, triggered in checks if triggered]


def build_outlier_features(session: MeasurementSession) -> list[float] | None:
    """Returns None when weather or delta is missing: the forest cannot score an
    incomplete upload, and the rule layer already reports why it is incomplete."""
    if session.weather is None or session.delta_c is None or len(session.readings) < 2:
        return None
    temps = _temperatures(session.readings)
    return [
        session.delta_c,
        session.weather.radiation_wm2,
        session.weather.wind_ms,
        float(len(temps)),
        statistics.pstdev(temps),
    ]


def build_outlier_training_set(
    observed: Sequence[MeasurementSession] = (),
) -> list[MeasurementSession]:
    """observed carries trusted seed uploads supplied by the caller; ml has no database
    access. Three seed roofs alone are far too few, so simulated sessions fill the set."""
    return generate_measurement_sessions() + list(observed)


def fit_outlier_model(sessions: Sequence[MeasurementSession]) -> IsolationForest:
    features = [f for f in map(build_outlier_features, sessions) if f is not None]
    if len(features) < MIN_OUTLIER_TRAINING_SESSIONS:
        raise InsufficientOutlierTrainingDataError(
            f"At least {MIN_OUTLIER_TRAINING_SESSIONS} complete sessions are required, "
            f"got {len(features)}."
        )
    model = IsolationForest(
        n_estimators=ISOLATION_TREE_COUNT,
        contamination=OUTLIER_CONTAMINATION,
        random_state=OUTLIER_RANDOM_STATE,
    )
    return model.fit(features)


@lru_cache(maxsize=1)
def default_outlier_model() -> IsolationForest:
    return fit_outlier_model(build_outlier_training_set())


def score_session(
    session: MeasurementSession, model: IsolationForest
) -> tuple[list[AnomalyFlag], float | None]:
    """The score is IsolationForest's decision function: below zero means outlier, and
    the further below, the more isolated the upload is from normal ones."""
    features = build_outlier_features(session)
    if features is None:
        return [], None
    is_outlier = model.predict([features])[0] == IS_OUTLIER
    score = float(model.decision_function([features])[0])
    return ([AnomalyFlag.STATISTICAL_OUTLIER] if is_outlier else []), score


def assess_measurement(
    session: MeasurementSession,
    history: Sequence[MeasurementSession],
    model: IsolationForest | None = None,
) -> AnomalyReport:
    rule_flags = detect_anomalies(
        session.readings,
        session.weather,
        history,
        device_id=session.device_id,
        delta_c=session.delta_c,
    )
    statistical_flags, score = score_session(
        session, default_outlier_model() if model is None else model
    )
    return AnomalyReport(
        rule_flags=tuple(rule_flags),
        statistical_flags=tuple(statistical_flags),
        outlier_score=score,
    )
