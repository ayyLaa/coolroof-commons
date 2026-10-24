from datetime import datetime

import pytest
from sklearn.pipeline import Pipeline

from ml.conditions import InvalidObservationError, Reading, RoofObservation, Weather, clock_hour
from ml.normalization import (
    STANDARD_HOUR_OF_DAY,
    STANDARD_WEATHER,
    InsufficientTrainingDataError,
    build_training_samples,
    compute_normalized_delta,
    default_model,
    fit_normalization_model,
    normalize,
)
from ml.physical_model import equilibrium_surface_temp
from ml.synthetic_series import generate_training_observations

CLOUDY_MORNING = Weather(ambient_c=28.0, radiation_wm2=350.0, wind_ms=3.0)
SUNNY_AFTERNOON = Weather(ambient_c=34.0, radiation_wm2=900.0, wind_ms=1.5)
DARK_ALBEDO = 0.12
COATED_ALBEDO = 0.70
# The regression approximates the physics; within this margin it is fit for verification,
# compared with the tens of degrees the raw delta is off by in these scenarios.
TOLERANCE_C = 3.0


@pytest.fixture(scope="module")
def model() -> Pipeline:
    return default_model()


@pytest.fixture
def seed_observations() -> list[RoofObservation]:
    """Mirrors the before-measurements of the scripts/seed.py demo roofs."""
    return [
        RoofObservation(
            Reading(datetime(2026, 6, 1, 13), 61.6), Weather(34.0, 850.0, 3.0), 0.12, 13.0
        ),
        RoofObservation(
            Reading(datetime(2026, 6, 5, 13), 61.0), Weather(31.0, 800.0, 3.0), 0.13, 13.0
        ),
        RoofObservation(
            Reading(datetime(2026, 6, 10, 13), 59.8), Weather(32.0, 820.0, 3.0), 0.11, 13.0
        ),
    ]


def observe(weather: Weather, albedo: float, measured_at: datetime) -> RoofObservation:
    reading = Reading(measured_at, equilibrium_surface_temp(weather, albedo))
    return RoofObservation(
        reading=reading, weather=weather, albedo=albedo, local_hour=clock_hour(measured_at)
    )


def standard_delta(albedo_before: float, albedo_after: float) -> float:
    return equilibrium_surface_temp(STANDARD_WEATHER, albedo_after) - equilibrium_surface_temp(
        STANDARD_WEATHER, albedo_before
    )


def test_reading_at_standard_conditions_is_unchanged(model: Pipeline) -> None:
    reading = Reading(datetime(2026, 7, 1, 13), 55.0)

    normalized = normalize(
        reading, STANDARD_WEATHER, albedo=0.3, local_hour=STANDARD_HOUR_OF_DAY, model=model
    )

    assert normalized == pytest.approx(55.0)


def test_weather_gaming_does_not_hide_missing_coating(model: Pipeline) -> None:
    before = observe(CLOUDY_MORNING, DARK_ALBEDO, datetime(2026, 6, 1, 10))
    after = observe(SUNNY_AFTERNOON, DARK_ALBEDO, datetime(2026, 7, 1, 14))
    raw_delta = after.reading.surface_temp_c - before.reading.surface_temp_c

    assert raw_delta > 30
    assert compute_normalized_delta(before, after, model) == pytest.approx(0.0, abs=TOLERANCE_C)


def test_real_coating_effect_survives_worse_weather(model: Pipeline) -> None:
    before = observe(CLOUDY_MORNING, DARK_ALBEDO, datetime(2026, 6, 1, 10))
    after = observe(SUNNY_AFTERNOON, COATED_ALBEDO, datetime(2026, 7, 1, 14))
    expected = standard_delta(DARK_ALBEDO, COATED_ALBEDO)

    assert after.reading.surface_temp_c > before.reading.surface_temp_c
    assert compute_normalized_delta(before, after, model) == pytest.approx(
        expected, abs=TOLERANCE_C
    )


def test_training_set_includes_seed_observations(
    seed_observations: list[RoofObservation],
) -> None:
    samples = build_training_samples(seed_observations)

    assert len(samples) == len(generate_training_observations()) + len(seed_observations)
    assert samples[-len(seed_observations) :] == seed_observations


def test_model_fits_with_seed_observations(seed_observations: list[RoofObservation]) -> None:
    samples = generate_training_observations(day_count=20) + seed_observations
    model = fit_normalization_model(samples)
    reading = seed_observations[0].reading

    normalized = normalize(reading, seed_observations[0].weather, DARK_ALBEDO, 13.0, model)

    assert normalized == pytest.approx(reading.surface_temp_c, abs=10.0)


def test_fit_rejects_too_few_samples(seed_observations: list[RoofObservation]) -> None:
    with pytest.raises(InsufficientTrainingDataError):
        fit_normalization_model(seed_observations[:1])


def test_normalize_rejects_invalid_albedo(model: Pipeline) -> None:
    with pytest.raises(InvalidObservationError):
        normalize(Reading(datetime(2026, 7, 1, 13), 50.0), STANDARD_WEATHER, 1.2, 13.0, model)


# Regression: ml receives the LOCAL hour as a parameter and never reads it from a
# timestamp. 13:00 in Athens summer is 10:00 UTC; passing the UTC hour must not go
# unnoticed.
ATHENS_SUMMER_UTC_OFFSET_H = 3


def test_utc_and_local_hour_give_different_results(model: Pipeline) -> None:
    reading = Reading(datetime(2026, 7, 15, 10), 58.0)
    local = normalize(reading, SUNNY_AFTERNOON, DARK_ALBEDO, 13.0, model)
    as_utc = normalize(
        reading, SUNNY_AFTERNOON, DARK_ALBEDO, 13.0 - ATHENS_SUMMER_UTC_OFFSET_H, model
    )

    assert local != pytest.approx(as_utc, abs=1e-6)


def test_local_interpretation_is_correct(model: Pipeline) -> None:
    """A reading taken at the standard local hour under standard weather is already
    standardised, so normalisation must return it unchanged. Only the local hour does;
    the UTC hour of the same moment (10:00) applies a spurious time-of-day correction."""
    reading = Reading(datetime(2026, 7, 15, 10), 55.0)

    local = normalize(reading, STANDARD_WEATHER, 0.3, STANDARD_HOUR_OF_DAY, model)
    as_utc = normalize(
        reading, STANDARD_WEATHER, 0.3, STANDARD_HOUR_OF_DAY - ATHENS_SUMMER_UTC_OFFSET_H, model
    )

    assert local == pytest.approx(55.0)
    assert as_utc != pytest.approx(55.0, abs=1e-3)
