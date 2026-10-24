"""Metrics behind the "why is AI needed" answer: anomaly detection quality and how
much normalisation stabilises the before/after delta across weather.

Everything here runs on SIMULATED data (synthetic sessions, injected anomalies,
physical-model temperatures, plus the simulated demo seed); results describe the
method's behaviour, not field performance.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sklearn.ensemble import IsolationForest

from ml.anomaly import default_outlier_model, detect_anomalies, score_session
from ml.conditions import MeasurementSession, Reading, RoofObservation, Weather, clock_hour
from ml.normalization import STANDARD_WEATHER, compute_normalized_delta
from ml.physical_model import equilibrium_surface_temp
from ml.synthetic_series import generate_measurement_sessions

SIMULATED = "simulated"
# Different from the training seed, so detectors are scored on sessions they never saw.
EVALUATION_SEED = 2026
HONEST_SESSION_COUNT = 200
ANOMALIES_PER_KIND = 20
FROZEN_RUN = 6
JUMP_C = 15.0
GAP = timedelta(minutes=6)
TOO_FEW_COUNT = 8
NOISY_SENSOR_STD_C = 2.5
REPLAY_SHIFT = timedelta(days=30)
SHADOW_WEATHER = Weather(ambient_c=29.0, radiation_wm2=220.0, wind_ms=3.0)
SHADOW_DELTA_C = -14.0
# Plausible-looking upload whose cooling the weather cannot explain; no single rule
# threshold is crossed.
IMPLAUSIBLE_WEATHER = Weather(ambient_c=30.0, radiation_wm2=450.0, wind_ms=6.0)
IMPLAUSIBLE_DELTA_C = -30.0
DECIMALS = 3
REPLAY_KIND = "replayed_upload"


@dataclass(frozen=True)
class LabelledSession:
    session: MeasurementSession
    is_anomaly: bool
    kind: str


def _with_temps(session: MeasurementSession, temps: Sequence[float]) -> MeasurementSession:
    readings = tuple(
        Reading(r.measured_at, t) for r, t in zip(session.readings, temps, strict=True)
    )
    return replace(session, readings=readings)


def _temps(session: MeasurementSession) -> list[float]:
    return [r.surface_temp_c for r in session.readings]


def frozen_sensor(session: MeasurementSession, rng: random.Random) -> MeasurementSession:
    temps = _temps(session)
    start = rng.randrange(0, len(temps) - FROZEN_RUN)
    temps[start : start + FROZEN_RUN] = [temps[start]] * FROZEN_RUN
    return _with_temps(session, temps)


def impossible_jump(session: MeasurementSession, rng: random.Random) -> MeasurementSession:
    temps = _temps(session)
    temps[rng.randrange(1, len(temps))] += JUMP_C
    return _with_temps(session, temps)


def timestamp_gap(session: MeasurementSession, rng: random.Random) -> MeasurementSession:
    split = rng.randrange(1, len(session.readings))
    readings = tuple(
        Reading(r.measured_at + (GAP if i >= split else timedelta()), r.surface_temp_c)
        for i, r in enumerate(session.readings)
    )
    return replace(session, readings=readings)


def too_few_readings(session: MeasurementSession, _: random.Random) -> MeasurementSession:
    return replace(session, readings=session.readings[:TOO_FEW_COUNT])


def noisy_sensor(session: MeasurementSession, rng: random.Random) -> MeasurementSession:
    return _with_temps(session, [t + rng.gauss(0, NOISY_SENSOR_STD_C) for t in _temps(session)])


def shadowed_probe(session: MeasurementSession, _: random.Random) -> MeasurementSession:
    return replace(session, weather=SHADOW_WEATHER, delta_c=SHADOW_DELTA_C)


def implausible_cooling(session: MeasurementSession, _: random.Random) -> MeasurementSession:
    return replace(session, weather=IMPLAUSIBLE_WEATHER, delta_c=IMPLAUSIBLE_DELTA_C)


def replayed_upload(session: MeasurementSession, _: random.Random) -> MeasurementSession:
    readings = tuple(
        Reading(r.measured_at + REPLAY_SHIFT, r.surface_temp_c) for r in session.readings
    )
    return replace(session, readings=readings)


def missing_weather(session: MeasurementSession, _: random.Random) -> MeasurementSession:
    return replace(session, weather=None)


INJECTORS: dict[str, Callable[[MeasurementSession, random.Random], MeasurementSession]] = {
    "frozen_sensor": frozen_sensor,
    "impossible_jump": impossible_jump,
    "timestamp_gap": timestamp_gap,
    "too_few_readings": too_few_readings,
    "noisy_sensor": noisy_sensor,
    "shadowed_probe": shadowed_probe,
    "implausible_cooling": implausible_cooling,
    REPLAY_KIND: replayed_upload,
    "missing_weather": missing_weather,
}


def build_labelled_sessions(
    honest: Sequence[MeasurementSession], rng: random.Random
) -> list[LabelledSession]:
    """Injected sessions reuse honest readings; all but the replay get their own device
    id, or every injected kind would also be caught as a replay of its base session."""
    labelled = [LabelledSession(session, False, "honest") for session in honest]
    for kind, inject in INJECTORS.items():
        for base in rng.sample(list(honest), ANOMALIES_PER_KIND):
            injected = inject(base, rng)
            if kind != REPLAY_KIND:
                injected = replace(injected, device_id=f"SIM-{kind}")
            labelled.append(LabelledSession(injected, True, kind))
    return labelled


def confusion_metrics(predicted: Sequence[bool], actual: Sequence[bool]) -> dict:
    pairs = list(zip(predicted, actual, strict=True))
    tp = sum(p and a for p, a in pairs)
    fp = sum(p and not a for p, a in pairs)
    fn = sum(a and not p for p, a in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, DECIMALS),
        "recall": round(recall, DECIMALS),
    }


def run_detectors(
    item: LabelledSession, history: Sequence[MeasurementSession], model: IsolationForest
) -> tuple[bool, bool]:
    """History excludes the session itself, otherwise every upload replays itself."""
    session = item.session
    others = [past for past in history if past is not session]
    rules = detect_anomalies(
        session.readings,
        session.weather,
        others,
        device_id=session.device_id,
        delta_c=session.delta_c,
    )
    statistical_flags, _ = score_session(session, model)
    return bool(rules), bool(statistical_flags)


def _detection_rates(rows: list[tuple[LabelledSession, bool, bool]]) -> dict:
    kinds = sorted({item.kind for item, _, _ in rows})
    rates = {}
    for kind in kinds:
        subset = [(rule, ml) for item, rule, ml in rows if item.kind == kind]
        rates[kind] = {
            "n": len(subset),
            "rules": round(sum(rule for rule, _ in subset) / len(subset), DECIMALS),
            "isolation_forest": round(sum(ml for _, ml in subset) / len(subset), DECIMALS),
        }
    return rates


def evaluate_anomaly_detection(
    seed_sessions: Sequence[LabelledSession] = (),
    model: IsolationForest | None = None,
    seed: int = EVALUATION_SEED,
) -> dict:
    """seed_sessions carries the demo seed uploads with their known labels; the bulk of
    the evaluation set is simulated because three roofs cannot yield precision/recall."""
    model = default_outlier_model() if model is None else model
    honest = generate_measurement_sessions(count=HONEST_SESSION_COUNT, seed=seed)
    labelled = build_labelled_sessions(honest, random.Random(seed)) + list(seed_sessions)
    history = honest + [item.session for item in seed_sessions]
    rows = [(item, *run_detectors(item, history, model)) for item in labelled]
    actual = [item.is_anomaly for item, _, _ in rows]
    return {
        "data_source": SIMULATED,
        "sessions": len(rows),
        "anomalies": sum(actual),
        "rules": confusion_metrics([rule for _, rule, _ in rows], actual),
        "isolation_forest": confusion_metrics([ml for _, _, ml in rows], actual),
        "combined": confusion_metrics([rule or ml for _, rule, ml in rows], actual),
        "detection_rate_by_kind": _detection_rates(rows),
    }


def _summary(values: Sequence[float]) -> dict:
    return {
        "mean_c": round(statistics.fmean(values), 2),
        "std_c": round(statistics.pstdev(values), 2),
        "min_c": round(min(values), 2),
        "max_c": round(max(values), 2),
        "range_c": round(max(values) - min(values), 2),
    }


def _observation(moment: datetime, weather: Weather, albedo: float) -> RoofObservation:
    temp = equilibrium_surface_temp(weather, albedo)
    return RoofObservation(Reading(moment, temp), weather, albedo, local_hour=clock_hour(moment))


def _normalization_scenario(
    before: RoofObservation, moment: datetime, weather: Weather, albedo: float
) -> dict:
    after = _observation(moment, weather, albedo)
    return {
        "after_measured_at": moment.isoformat(),
        "ambient_c": weather.ambient_c,
        "radiation_wm2": weather.radiation_wm2,
        "wind_ms": weather.wind_ms,
        "raw_delta_c": round(after.reading.surface_temp_c - before.reading.surface_temp_c, 2),
        "normalized_delta_c": round(compute_normalized_delta(before, after), 2),
    }


def normalization_stability(
    before: tuple[datetime, Weather],
    after_conditions: Sequence[tuple[datetime, Weather]],
    albedo_before: float,
    albedo_after: float,
) -> dict:
    """Same roof, same coating, only the after-measurement weather changes. A good
    normalisation keeps the delta nearly constant while the raw delta swings."""
    before_obs = _observation(*before, albedo_before)
    if not after_conditions:
        raise ValueError("At least one after-measurement condition is required.")
    scenarios = [
        _normalization_scenario(before_obs, moment, weather, albedo_after)
        for moment, weather in after_conditions
    ]
    raw = _summary([s["raw_delta_c"] for s in scenarios])
    normalized = _summary([s["normalized_delta_c"] for s in scenarios])
    true_delta = equilibrium_surface_temp(
        STANDARD_WEATHER, albedo_after
    ) - equilibrium_surface_temp(STANDARD_WEATHER, albedo_before)
    return {
        "data_source": SIMULATED,
        "albedo_before": albedo_before,
        "albedo_after": albedo_after,
        "true_delta_at_standard_c": round(true_delta, 2),
        "raw_delta": raw,
        "normalized_delta": normalized,
        "spread_reduction_factor": round(raw["std_c"] / normalized["std_c"], 1)
        if normalized["std_c"]
        else None,
        "scenarios": scenarios,
    }
