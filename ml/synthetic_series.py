"""Synthetic surface temperature series: training data and demo before/after curves.

This project runs no physical experiment: there is no field campaign measuring the same
roof under many weather conditions. Every series below is SIMULATED by driving
ml.physical_model with weather and adding sensor noise. Training series use plausible
invented Athens summer days; demo series use REAL hourly weather passed in by the
caller, but the surface temperatures they contain are still simulated. Demo readings
therefore always carry data_source="simulated" and must never be shown as measured.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ml.conditions import (
    InvalidObservationError,
    MeasurementSession,
    Reading,
    RoofObservation,
    Weather,
    clock_hour,
)
from ml.physical_model import equilibrium_surface_temp, simulate_surface_curve

SYNTHETIC_DAY_COUNT = 400
RANDOM_SEED = 7
SERIES_START = datetime(2026, 6, 1)
STEP_MINUTES = 15
STEPS_PER_DAY = 24 * 60 // STEP_MINUTES

# Athens summer, local time: sunrise ~06:00, sunset ~20:30, warmest around 15:00.
SUNRISE_H = 6.0
SUNSET_H = 20.5
AMBIENT_PEAK_H = 15.0
HOURS_PER_DAY = 24.0
# Only hours in which a field technician could realistically measure become samples.
MEASUREMENT_WINDOW_H = (8.0, 18.0)

PEAK_AMBIENT_C_RANGE = (22.0, 40.0)
DIURNAL_SWING_C_RANGE = (6.0, 12.0)
CLEAR_SKY_PEAK_RADIATION_WM2 = 950.0
# Daily cloudiness as the fraction of clear-sky radiation reaching the roof.
DAILY_TRANSMITTANCE_RANGE = (0.3, 1.0)
# Passing clouds within a day, so radiation is not a pure function of hour.
STEP_TRANSMITTANCE_RANGE = (0.75, 1.0)
WIND_MS_RANGE = (0.5, 8.0)
WIND_GUST_STD_MS = 0.8
ALBEDO_RANGE = (0.05, 0.85)
SENSOR_NOISE_STD_C = 0.5

# Measurement sessions, shaped like the scripts/seed.py probe curves.
SESSION_COUNT = 500
SESSION_START = datetime(2026, 6, 1, 13)
SESSION_READING_COUNT = 16
SESSION_STEP_MINUTES = 1
SESSION_WARMUP_RATE_PER_STEP = 0.35
SESSION_WARMUP_C_RANGE = (1.0, 4.0)
SESSION_NOISE_STD_C = 0.25
SYNTHETIC_DEVICE_ID = "SIM-0000"
UNCOATED_ALBEDO_RANGE = (0.05, 0.25)
# Starts low on purpose: poor coatings are legitimate uploads, not anomalies.
COATED_ALBEDO_RANGE = (0.2, 0.85)
# Before and after visits are scheduled for similar clear summer middays, so the after
# weather is the before weather plus a modest day-to-day drift.
SESSION_RADIATION_WM2_RANGE = (600.0, 950.0)
SESSION_AMBIENT_DRIFT_STD_C = 2.0
SESSION_RADIATION_DRIFT_STD_WM2 = 60.0
SESSION_WIND_DRIFT_STD_MS = 1.0

# Demo series: one 15-minute probe session sampled every 30 seconds.
SIMULATED = "simulated"
DEMO_SESSION = timedelta(minutes=15)
DEMO_STEP = timedelta(seconds=30)
# The roof's thermal state depends on the preceding hours; simulating from this far
# back lets the lagged model settle before the session starts.
DEMO_SPIN_UP = timedelta(hours=3)
# Sensor accuracy of +/-0.3 C read as a 95% bound, i.e. 1.96 standard deviations.
SENSOR_ACCURACY_C = 0.3
SENSOR_ACCURACY_Z = 1.96


@dataclass(frozen=True)
class DayParameters:
    peak_ambient_c: float
    diurnal_swing_c: float
    transmittance: float
    mean_wind_ms: float
    albedo: float


def sample_day_parameters(rng: random.Random) -> DayParameters:
    return DayParameters(
        peak_ambient_c=rng.uniform(*PEAK_AMBIENT_C_RANGE),
        diurnal_swing_c=rng.uniform(*DIURNAL_SWING_C_RANGE),
        transmittance=rng.uniform(*DAILY_TRANSMITTANCE_RANGE),
        mean_wind_ms=rng.uniform(*WIND_MS_RANGE),
        albedo=rng.uniform(*ALBEDO_RANGE),
    )


def clear_sky_radiation(hour: float) -> float:
    if not SUNRISE_H < hour < SUNSET_H:
        return 0.0
    solar_phase = math.pi * (hour - SUNRISE_H) / (SUNSET_H - SUNRISE_H)
    return CLEAR_SKY_PEAK_RADIATION_WM2 * math.sin(solar_phase)


def ambient_temperature(hour: float, day: DayParameters) -> float:
    phase = 2 * math.pi * (hour - AMBIENT_PEAK_H) / HOURS_PER_DAY
    return day.peak_ambient_c - day.diurnal_swing_c / 2 * (1 - math.cos(phase))


def build_day_weather(
    day: DayParameters, day_start: datetime, rng: random.Random
) -> list[tuple[datetime, Weather]]:
    series = []
    for step in range(STEPS_PER_DAY):
        timestamp = day_start + timedelta(minutes=step * STEP_MINUTES)
        hour = step * STEP_MINUTES / 60
        cloud_factor = day.transmittance * rng.uniform(*STEP_TRANSMITTANCE_RANGE)
        weather = Weather(
            ambient_c=ambient_temperature(hour, day),
            radiation_wm2=clear_sky_radiation(hour) * cloud_factor,
            wind_ms=max(0.0, rng.gauss(day.mean_wind_ms, WIND_GUST_STD_MS)),
        )
        series.append((timestamp, weather))
    return series


def _in_measurement_window(timestamp: datetime) -> bool:
    hour = timestamp.hour + timestamp.minute / 60
    return MEASUREMENT_WINDOW_H[0] <= hour <= MEASUREMENT_WINDOW_H[1]


def simulate_day(
    day: DayParameters, day_start: datetime, rng: random.Random
) -> list[RoofObservation]:
    weather_series = build_day_weather(day, day_start, rng)
    curve = simulate_surface_curve(weather_series, day.albedo)
    return [
        RoofObservation(
            reading=Reading(
                measured_at=timestamp,
                surface_temp_c=point.surface_temp_c + rng.gauss(0, SENSOR_NOISE_STD_C),
            ),
            weather=weather,
            albedo=day.albedo,
            local_hour=clock_hour(timestamp),
        )
        for (timestamp, weather), point in zip(weather_series, curve.points)
        if _in_measurement_window(timestamp)
    ]


def simulate_session_readings(
    plateau_c: float, start: datetime, rng: random.Random
) -> tuple[Reading, ...]:
    """The probe starts below the surface temperature and settles onto it, the shape
    real contact sensors show and the demo seed curves follow."""
    warmup_c = rng.uniform(*SESSION_WARMUP_C_RANGE)
    readings = []
    for step in range(SESSION_READING_COUNT):
        progress = 1 - math.exp(-SESSION_WARMUP_RATE_PER_STEP * step)
        temp_c = plateau_c - warmup_c * (1 - progress) + rng.gauss(0, SESSION_NOISE_STD_C)
        timestamp = start + timedelta(minutes=step * SESSION_STEP_MINUTES)
        readings.append(Reading(measured_at=timestamp, surface_temp_c=round(temp_c, 2)))
    return tuple(readings)


def sample_session_weather(rng: random.Random) -> Weather:
    return Weather(
        ambient_c=rng.uniform(*PEAK_AMBIENT_C_RANGE),
        radiation_wm2=rng.uniform(*SESSION_RADIATION_WM2_RANGE),
        wind_ms=rng.uniform(*WIND_MS_RANGE),
    )


def drift_weather(weather: Weather, rng: random.Random) -> Weather:
    return Weather(
        ambient_c=weather.ambient_c + rng.gauss(0, SESSION_AMBIENT_DRIFT_STD_C),
        radiation_wm2=max(
            0.0, weather.radiation_wm2 + rng.gauss(0, SESSION_RADIATION_DRIFT_STD_WM2)
        ),
        wind_ms=max(0.0, weather.wind_ms + rng.gauss(0, SESSION_WIND_DRIFT_STD_MS)),
    )


def simulate_measurement_session(start: datetime, rng: random.Random) -> MeasurementSession:
    before_weather = sample_session_weather(rng)
    after_weather = drift_weather(before_weather, rng)
    before_c = equilibrium_surface_temp(before_weather, rng.uniform(*UNCOATED_ALBEDO_RANGE))
    after_c = equilibrium_surface_temp(after_weather, rng.uniform(*COATED_ALBEDO_RANGE))
    return MeasurementSession(
        device_id=SYNTHETIC_DEVICE_ID,
        readings=simulate_session_readings(after_c, start, rng),
        weather=after_weather,
        delta_c=after_c - before_c,
    )


def generate_measurement_sessions(
    count: int = SESSION_COUNT, seed: int = RANDOM_SEED
) -> list[MeasurementSession]:
    """Simulated, like the training observations: honest after-measurements of coated
    roofs under varied weather, the reference of what normal uploads look like."""
    rng = random.Random(seed)
    return [
        simulate_measurement_session(SESSION_START + timedelta(days=index), rng)
        for index in range(count)
    ]


def generate_training_observations(
    day_count: int = SYNTHETIC_DAY_COUNT, seed: int = RANDOM_SEED
) -> list[RoofObservation]:
    """Seeded so the trained model, and every normalised delta derived from it, is
    reproducible: verification results must not change between runs."""
    rng = random.Random(seed)
    observations: list[RoofObservation] = []
    for day_index in range(day_count):
        day_start = SERIES_START + timedelta(days=day_index)
        observations.extend(simulate_day(sample_day_parameters(rng), day_start, rng))
    return observations


@dataclass(frozen=True)
class SimulatedReading:
    timestamp: datetime
    surface_temp_c: float
    data_source: str = field(default=SIMULATED, init=False)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "surface_temp_c": self.surface_temp_c,
            "data_source": self.data_source,
        }


def interpolate_weather(hourly: Sequence[tuple[datetime, Weather]], moment: datetime) -> Weather:
    """Linear between the two surrounding hours; Open-Meteo only reports full hours but
    the demo samples every 30 seconds."""
    for (t0, w0), (t1, w1) in zip(hourly, hourly[1:]):
        if t0 <= moment <= t1:
            share = (moment - t0) / (t1 - t0)
            return Weather(
                ambient_c=w0.ambient_c + share * (w1.ambient_c - w0.ambient_c),
                radiation_wm2=w0.radiation_wm2 + share * (w1.radiation_wm2 - w0.radiation_wm2),
                wind_ms=w0.wind_ms + share * (w1.wind_ms - w0.wind_ms),
            )
    raise InvalidObservationError(f"No hourly weather surrounds {moment.isoformat()}.")


def simulate_probe_session(
    hourly: Sequence[tuple[datetime, Weather]], start: datetime, albedo: float, rng: random.Random
) -> tuple[SimulatedReading, ...]:
    steps = int((DEMO_SPIN_UP + DEMO_SESSION) / DEMO_STEP)
    times = [start - DEMO_SPIN_UP + i * DEMO_STEP for i in range(steps + 1)]
    curve = simulate_surface_curve([(t, interpolate_weather(hourly, t)) for t in times], albedo)
    noise_std = SENSOR_ACCURACY_C / SENSOR_ACCURACY_Z
    return tuple(
        SimulatedReading(
            timestamp=point.timestamp,
            surface_temp_c=round(point.surface_temp_c + rng.gauss(0, noise_std), 2),
        )
        for point in curve.points
        if point.timestamp >= start
    )


def generate_before_after_series(
    hourly: Sequence[tuple[datetime, Weather]],
    before_start: datetime,
    after_start: datetime,
    albedo_before: float,
    albedo_after: float,
    seed: int = RANDOM_SEED,
) -> dict:
    """hourly must be sorted real weather covering both sessions plus the spin-up."""
    rng = random.Random(seed)
    sessions = {
        "before": (before_start, albedo_before),
        "after": (after_start, albedo_after),
    }
    return {
        "data_source": SIMULATED,
        **{
            phase: {
                "start": start.isoformat(),
                "albedo": albedo,
                "readings": [
                    r.to_dict() for r in simulate_probe_session(hourly, start, albedo, rng)
                ],
            }
            for phase, (start, albedo) in sessions.items()
        },
    }
