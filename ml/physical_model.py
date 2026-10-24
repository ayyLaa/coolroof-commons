"""Fallback roof surface temperature model based on a simple energy balance.

Used where no measured series exists: it turns real weather into a plausible surface
temperature curve. Its output is never a measurement, so every result is labelled
simulated and must not be presented or verified as sensor data.

Balance per unit roof area, at equilibrium:
    absorbed solar = heat loss to the surroundings
    (1 - albedo) * radiation = h * (T_surface - T_ambient)
    T_surface = T_ambient + (1 - albedo) * radiation / h
h is mostly wind-driven convection plus a constant, linearised longwave term:
without it a dark roof in still air under full sun would exceed 100 C. Conduction into
the building is neglected, which keeps dark roofs slightly too hot; fine for a fallback.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from ml.conditions import InvalidObservationError, Weather, validate_albedo

# Wind-dependent convective coefficient h = a + b * wind (W/m2K), the classic
# McAdams/Juerges correlation for flat plates in open air.
CONVECTION_BASE_W_M2K = 5.7
CONVECTION_WIND_W_M2K_PER_MS = 3.8
# Longwave exchange linearised around summer roof temperatures: 4 * emissivity * sigma * T^3
# with emissivity 0.9 and T ~ 310 K gives ~6 W/m2K, added to h as a constant.
LINEARISED_LONGWAVE_W_M2K = 6.0
# A roof does not jump to equilibrium: its thermal mass makes it relax towards it.
# Under an hour matches the fast response of a roof's thin outer layer.
THERMAL_TIME_CONSTANT_H = 0.75
SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class SimulatedPoint:
    timestamp: datetime
    surface_temp_c: float


@dataclass(frozen=True)
class SimulatedSeries:
    points: tuple[SimulatedPoint, ...]
    simulated: bool = field(default=True, init=False)

    def to_dict(self) -> dict:
        return {
            "simulated": self.simulated,
            "points": [
                {"timestamp": point.timestamp.isoformat(), "surface_temp_c": point.surface_temp_c}
                for point in self.points
            ],
        }


def heat_loss_coefficient(wind_ms: float) -> float:
    if wind_ms < 0:
        raise InvalidObservationError(f"wind_ms must be >= 0, got {wind_ms}.")
    convection = CONVECTION_BASE_W_M2K + CONVECTION_WIND_W_M2K_PER_MS * wind_ms
    return convection + LINEARISED_LONGWAVE_W_M2K


def absorbed_radiation(weather: Weather, albedo: float) -> float:
    return (1.0 - albedo) * max(weather.radiation_wm2, 0.0)


def equilibrium_surface_temp(weather: Weather, albedo: float) -> float:
    validate_albedo(albedo)
    return weather.ambient_c + absorbed_radiation(weather, albedo) / heat_loss_coefficient(
        weather.wind_ms
    )


def relax_towards(current_c: float, target_c: float, elapsed_h: float) -> float:
    decay = math.exp(-elapsed_h / THERMAL_TIME_CONSTANT_H)
    return target_c + (current_c - target_c) * decay


def _elapsed_hours(previous: datetime, current: datetime) -> float:
    elapsed_h = (current - previous).total_seconds() / SECONDS_PER_HOUR
    if elapsed_h <= 0:
        raise InvalidObservationError("Weather timestamps must be strictly increasing.")
    return elapsed_h


def simulate_surface_curve(
    weather_series: Sequence[tuple[datetime, Weather]], albedo: float
) -> SimulatedSeries:
    """The first point starts at equilibrium; every later point relaxes from the previous
    temperature, which reproduces morning lag and afternoon carry-over of heat."""
    validate_albedo(albedo)
    points: list[SimulatedPoint] = []
    for timestamp, weather in weather_series:
        target_c = equilibrium_surface_temp(weather, albedo)
        if points:
            elapsed_h = _elapsed_hours(points[-1].timestamp, timestamp)
            target_c = relax_towards(points[-1].surface_temp_c, target_c, elapsed_h)
        points.append(SimulatedPoint(timestamp=timestamp, surface_temp_c=target_c))
    return SimulatedSeries(points=tuple(points))
