"""Reduces a roof surface temperature reading to standard weather conditions.

A "before" reading on a cloudy 10:00 morning and an "after" reading in 14:00 sunshine
are not comparable: the difference may come from the weather, not the coating, and
choosing measurement times that way is exactly how the system could be gamed. A Ridge
regression learns how weather moves surface temperature; each reading is then shifted
to what it would have been under the standard conditions below, so before and after
are compared like for like.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache

from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.conditions import Reading, RoofObservation, Weather, validate_albedo
from ml.physical_model import absorbed_radiation, heat_loss_coefficient
from ml.synthetic_series import generate_training_observations

STANDARD_AMBIENT_C = 30.0
STANDARD_RADIATION_WM2 = 850.0
STANDARD_WIND_MS = 2.0
# Solar noon in Athens summer local time is ~13:20; 13:00 sits in the hottest
# measurable window and is the hour the standard radiation level is plausible for.
STANDARD_HOUR_OF_DAY = 13.0
STANDARD_WEATHER = Weather(
    ambient_c=STANDARD_AMBIENT_C, radiation_wm2=STANDARD_RADIATION_WM2, wind_ms=STANDARD_WIND_MS
)
HOURS_PER_DAY = 24.0
# Mild shrinkage: features are few and well conditioned after scaling, so the penalty
# only has to keep coefficients stable when a handful of seed samples are added.
RIDGE_ALPHA = 1.0
MIN_TRAINING_SAMPLES = 2


class InsufficientTrainingDataError(ValueError):
    """Raised when there are too few samples to fit the regression."""


def build_features(weather: Weather, hour: float, albedo: float) -> list[float]:
    """Hour is sin/cos encoded so 23:00 and 01:00 are neighbours. The last feature is the
    energy-balance heating term (1 - albedo) * radiation / h: a linear model of the raw
    inputs alone would apply the same sun correction to a black and a white roof and miss
    that wind divides, not subtracts from, solar heating. With it, an unchanged roof
    measured in cloud and then in sun normalises to a near-zero delta."""
    phase = 2 * math.pi * hour / HOURS_PER_DAY
    solar_heating_c = absorbed_radiation(weather, albedo) / heat_loss_coefficient(weather.wind_ms)
    return [
        weather.ambient_c,
        weather.radiation_wm2,
        weather.wind_ms,
        math.sin(phase),
        math.cos(phase),
        albedo,
        solar_heating_c,
    ]


def build_training_samples(observed: Sequence[RoofObservation] = ()) -> list[RoofObservation]:
    """observed carries real or seed measurements (e.g. scripts/seed.py roofs) supplied by
    the caller; ml stays free of database access and only receives the data."""
    return generate_training_observations() + list(observed)


def fit_normalization_model(samples: Sequence[RoofObservation]) -> Pipeline:
    if len(samples) < MIN_TRAINING_SAMPLES:
        raise InsufficientTrainingDataError(
            f"At least {MIN_TRAINING_SAMPLES} samples are required, got {len(samples)}."
        )
    features = [
        build_features(sample.weather, sample.local_hour, sample.albedo) for sample in samples
    ]
    targets = [sample.reading.surface_temp_c for sample in samples]
    return make_pipeline(StandardScaler(), Ridge(alpha=RIDGE_ALPHA)).fit(features, targets)


@lru_cache(maxsize=1)
def default_model() -> Pipeline:
    """Trained once per process; the synthetic series is seeded, so the result is the
    same deterministic model every time."""
    return fit_normalization_model(build_training_samples())


def predict_surface_temp(model: Pipeline, weather: Weather, hour: float, albedo: float) -> float:
    return float(model.predict([build_features(weather, hour, albedo)])[0])


def normalize(
    reading: Reading,
    weather: Weather,
    albedo: float,
    local_hour: float,
    model: Pipeline | None = None,
) -> float:
    """Only the weather-driven part is swapped: the model's prediction for the actual
    conditions is replaced by its prediction for standard conditions. The roof-specific
    residual the model cannot explain is kept, because that is the real signal."""
    validate_albedo(albedo)
    if model is None:
        model = default_model()
    actual_c = predict_surface_temp(model, weather, local_hour, albedo)
    standard_c = predict_surface_temp(model, STANDARD_WEATHER, STANDARD_HOUR_OF_DAY, albedo)
    return reading.surface_temp_c - actual_c + standard_c


def compute_normalized_delta(
    before: RoofObservation, after: RoofObservation, model: Pipeline | None = None
) -> float:
    """Negative values mean the roof became cooler under identical standard weather."""
    normalized_before = normalize(
        before.reading, before.weather, before.albedo, before.local_hour, model
    )
    normalized_after = normalize(
        after.reading, after.weather, after.albedo, after.local_hour, model
    )
    return normalized_after - normalized_before
