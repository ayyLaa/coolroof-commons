import random
from datetime import datetime, timedelta

import pytest

from ml.conditions import InvalidObservationError, Weather
from ml.synthetic_series import (
    ALBEDO_RANGE,
    MEASUREMENT_WINDOW_H,
    SENSOR_ACCURACY_C,
    clear_sky_radiation,
    generate_before_after_series,
    generate_training_observations,
    simulate_probe_session,
)


def test_series_is_reproducible() -> None:
    assert generate_training_observations(day_count=3) == generate_training_observations(
        day_count=3
    )


def test_observations_stay_in_measurement_window_and_ranges() -> None:
    observations = generate_training_observations(day_count=5)

    assert observations
    for observation in observations:
        hour = observation.reading.measured_at.hour + observation.reading.measured_at.minute / 60
        assert MEASUREMENT_WINDOW_H[0] <= hour <= MEASUREMENT_WINDOW_H[1]
        assert ALBEDO_RANGE[0] <= observation.albedo <= ALBEDO_RANGE[1]
        assert observation.weather.radiation_wm2 >= 0


@pytest.mark.parametrize("hour", [0.0, 3.0, 22.0])
def test_no_radiation_at_night(hour: float) -> None:
    assert clear_sky_radiation(hour) == 0.0


def test_zero_days_yield_no_observations() -> None:
    assert generate_training_observations(day_count=0) == []


HOURLY_WEATHER = [
    (
        datetime(2026, 7, 15, hour),
        Weather(ambient_c=30.0 + hour * 0.2, radiation_wm2=800.0, wind_ms=3.0),
    )
    for hour in range(6, 16)
]


def test_demo_session_is_fifteen_minutes_at_thirty_seconds() -> None:
    readings = simulate_probe_session(
        HOURLY_WEATHER, datetime(2026, 7, 15, 13), 0.12, random.Random(1)
    )

    assert len(readings) == 31
    assert readings[1].timestamp - readings[0].timestamp == timedelta(seconds=30)
    assert all(reading.data_source == "simulated" for reading in readings)


def test_every_demo_record_is_labelled_simulated() -> None:
    series = generate_before_after_series(
        HOURLY_WEATHER, datetime(2026, 7, 15, 10), datetime(2026, 7, 15, 13), 0.12, 0.75
    )

    assert series["data_source"] == "simulated"
    for phase in ("before", "after"):
        assert {r["data_source"] for r in series[phase]["readings"]} == {"simulated"}


def test_coated_roof_is_cooler_in_demo_series() -> None:
    start = datetime(2026, 7, 15, 13)
    series = generate_before_after_series(HOURLY_WEATHER, start, start, 0.12, 0.75)

    before_mean, after_mean = (
        sum(r["surface_temp_c"] for r in series[phase]["readings"]) / len(series[phase]["readings"])
        for phase in ("before", "after")
    )
    assert after_mean < before_mean - 10


def test_noise_is_seeded_and_within_sensor_accuracy() -> None:
    start = datetime(2026, 7, 15, 13)
    first = simulate_probe_session(HOURLY_WEATHER, start, 0.5, random.Random(3))
    second = simulate_probe_session(HOURLY_WEATHER, start, 0.5, random.Random(3))

    assert first == second
    temps = [r.surface_temp_c for r in first]
    assert max(temps) - min(temps) < 4 * SENSOR_ACCURACY_C


def test_weather_must_cover_the_session() -> None:
    with pytest.raises(InvalidObservationError):
        simulate_probe_session(HOURLY_WEATHER, datetime(2026, 7, 16, 13), 0.12, random.Random(1))
