import math
from datetime import datetime, timedelta

import pytest

from ml.conditions import InvalidObservationError, Weather
from ml.physical_model import (
    THERMAL_TIME_CONSTANT_H,
    SimulatedSeries,
    equilibrium_surface_temp,
    heat_loss_coefficient,
    relax_towards,
    simulate_surface_curve,
)

SUNNY = Weather(ambient_c=32.0, radiation_wm2=850.0, wind_ms=3.0)
NIGHT = Weather(ambient_c=24.0, radiation_wm2=0.0, wind_ms=3.0)


@pytest.fixture
def morning_weather() -> list[tuple[datetime, Weather]]:
    start = datetime(2026, 7, 1, 6)
    return [(start, NIGHT)] + [(start + timedelta(hours=h), SUNNY) for h in range(1, 6)]


def test_equilibrium_matches_energy_balance() -> None:
    expected = SUNNY.ambient_c + (1 - 0.2) * SUNNY.radiation_wm2 / heat_loss_coefficient(3.0)

    assert equilibrium_surface_temp(SUNNY, albedo=0.2) == pytest.approx(expected)


def test_no_sun_means_ambient_temperature() -> None:
    assert equilibrium_surface_temp(NIGHT, albedo=0.1) == pytest.approx(NIGHT.ambient_c)


def test_reflective_and_windy_roofs_are_cooler() -> None:
    dark = equilibrium_surface_temp(SUNNY, albedo=0.1)
    white = equilibrium_surface_temp(SUNNY, albedo=0.8)
    windy = equilibrium_surface_temp(Weather(32.0, 850.0, 8.0), albedo=0.1)

    assert white < dark
    assert windy < dark


def test_relaxation_after_one_time_constant() -> None:
    relaxed = relax_towards(current_c=0.0, target_c=10.0, elapsed_h=THERMAL_TIME_CONSTANT_H)

    assert relaxed == pytest.approx(10.0 * (1 - math.exp(-1)))


def test_curve_warms_towards_equilibrium(morning_weather: list[tuple[datetime, Weather]]) -> None:
    temps = [p.surface_temp_c for p in simulate_surface_curve(morning_weather, 0.15).points]

    assert temps == sorted(temps)
    assert temps[-1] == pytest.approx(equilibrium_surface_temp(SUNNY, 0.15), abs=0.1)


def test_output_is_always_labelled_simulated(
    morning_weather: list[tuple[datetime, Weather]],
) -> None:
    series = simulate_surface_curve(morning_weather, albedo=0.15)

    assert series.simulated is True
    assert series.to_dict()["simulated"] is True
    assert len(series.to_dict()["points"]) == len(morning_weather)


def test_simulated_flag_cannot_be_overridden() -> None:
    with pytest.raises(TypeError):
        SimulatedSeries(points=(), simulated=False)  # type: ignore[call-arg]


@pytest.mark.parametrize("albedo", [-0.1, 1.5])
def test_rejects_invalid_albedo(albedo: float) -> None:
    with pytest.raises(InvalidObservationError):
        equilibrium_surface_temp(SUNNY, albedo=albedo)


def test_rejects_negative_wind() -> None:
    with pytest.raises(InvalidObservationError):
        heat_loss_coefficient(-1.0)


def test_rejects_unordered_timestamps() -> None:
    now = datetime(2026, 7, 1, 12)
    with pytest.raises(InvalidObservationError):
        simulate_surface_curve([(now, SUNNY), (now - timedelta(hours=1), SUNNY)], albedo=0.2)
