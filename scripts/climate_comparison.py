"""CoolRoof Commons - seasonal benefit vs cost of a reflective roof, per pilot city.

A reflective coating absorbs less sunlight all year. In summer that is the benefit; in
winter it is a cost, because the roof no longer helps heat the building. Athens is hot
all summer with mild winters; London is usually cool, reached 40 C in the July 2022
heatwave and has a real heating season. That difference is why contract thresholds are
set per climate (schema/thresholds.json).

Two framings are computed from the same data and they rank the cities in opposite order:
- demand_weighted (primary): kept-out sunlight counts as a benefit only in hours that
  need cooling (> 24 C) and as a penalty only in hours that need heating (< 15.5 C).
  The real cost of a cool roof is the heating it causes, not the sunlight it reflects.
- solar_only (secondary): all summer sunlight is benefit, all winter sunlight penalty.
  It is kept for transparency; scripts/climate_framing.py explains why it misleads.

Everything here is a ROUGH, SIMULATED estimate (data_source "simulated"):
- energy = solar irradiation x (new albedo - old albedo), i.e. sunlight the roof no
  longer absorbs, per m2 of roof. How much of it would have reached the rooms depends
  on insulation, roof build-up, ventilation and whether the building is heated or cooled.
- surface cooling comes from the energy-balance model in ml/physical_model.py.
Inputs are real: hourly Open-Meteo weather (third-party data) and the cities' satellite-
measured roof albedo and areas. Only the outputs are modelled.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import ASSUMED_COATED_ALBEDO  # noqa: E402
from cities import CITIES, City, metrics_path  # noqa: E402
from climate_framing import (  # noqa: E402
    ASSUMPTIONS,
    COOLING_BASE_C,
    DEMAND_WEIGHTED,
    HEATING_BASE_C,
    SOLAR_ONLY,
    build_conclusion,
    heat_reference,
    method_descriptions,
    solar_only_note,
)
from fetch_satellite import INSTRUMENTS, PRIMARY_INSTRUMENT, ROOF_SETS  # noqa: E402
from fetch_weather import build_query, choose_endpoint, fetch_hourly, parse_hourly_records  # noqa: E402

from ml.conditions import Weather  # noqa: E402
from ml.physical_model import equilibrium_surface_temp  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "data" / "climate_comparison.json"
SIMULATED = "simulated"
WH_PER_KWH = 1000.0
# Hourly Open-Meteo radiation is the mean over the hour in W/m2, i.e. Wh/m2 per record.
HOURS_PER_RECORD = 1.0
# Daytime window in local time over which the summer surface cooling is averaged.
DAYTIME_LOCAL_HOURS = range(10, 17)
HOURS_PER_DAY = 24.0
DECIMALS = 2
CAVEAT = (
    "Rough estimate of sunlight absorbed at the roof surface, not of building energy use. "
    "See assumptions: the share that reaches the interior depends on insulation, and the "
    "summer figure only saves energy where the building is cooled."
)


def reference_point(city: City) -> tuple[float, float]:
    west, south, east, north = city.residential_bbox
    return (south + north) / 2, (west + east) / 2


def season_weather(city: City, season: tuple[str, str]) -> list[dict]:
    """Real hourly weather via the scripts/fetch_weather.py file cache."""
    start, end = date.fromisoformat(season[0]), date.fromisoformat(season[1])
    lat, lon = reference_point(city)
    url = choose_endpoint("auto", end, date.today())
    return parse_hourly_records(fetch_hourly(url, build_query(lat, lon, start, end), False))


def roof_metrics(city: City) -> list[dict]:
    """Measured albedo and area of the city's roofs, one row per roof (primary instrument)."""
    primary = INSTRUMENTS[PRIMARY_INSTRUMENT].name
    rows = []
    for roof_set in ROOF_SETS:
        path = metrics_path(city, roof_set)
        if path.exists():
            with path.open(newline="", encoding="utf-8") as handle:
                rows += [
                    r for r in csv.DictReader(handle) if r["instrument"] == primary and r["albedo"]
                ]
    if not rows:
        raise SystemExit(f"No satellite metrics for {city.name}; run scripts/fetch_satellite.py.")
    return rows


def irradiation_kwh_per_m2(records: list[dict]) -> float:
    return sum(r["radiation_wm2"] * HOURS_PER_RECORD for r in records) / WH_PER_KWH


def benefit_and_penalty(benefit_kwh: float, penalty_kwh: float) -> dict:
    return {
        "cooling_benefit_kwh_per_m2": round(benefit_kwh, 1),
        "heating_penalty_kwh_per_m2": round(penalty_kwh, 1),
        "net_benefit_kwh_per_m2": round(benefit_kwh - penalty_kwh, 1),
        "penalty_to_benefit_ratio": round(penalty_kwh / benefit_kwh, 3) if benefit_kwh else None,
    }


def demand_weighted(records: list[dict], albedo_change: float) -> dict:
    """Sunlight only matters for a building when there is demand for it: kept-out sunlight
    is a benefit in hours that need cooling and a penalty in hours that need heating.
    Both seasons are scanned, so a cold summer hour counts as a (small) penalty too."""
    cooling = [r for r in records if r["ambient_c"] > COOLING_BASE_C]
    heating = [r for r in records if r["ambient_c"] < HEATING_BASE_C]
    return {
        "cooling_base_c": COOLING_BASE_C,
        "heating_base_c": HEATING_BASE_C,
        **benefit_and_penalty(
            irradiation_kwh_per_m2(cooling) * albedo_change,
            irradiation_kwh_per_m2(heating) * albedo_change,
        ),
    }


def solar_only(summer: list[dict], winter: list[dict], albedo_change: float) -> dict:
    return benefit_and_penalty(
        irradiation_kwh_per_m2(summer) * albedo_change,
        irradiation_kwh_per_m2(winter) * albedo_change,
    )


def heating_degree_hours(records: list[dict]) -> float:
    return sum(max(0.0, HEATING_BASE_C - r["ambient_c"]) for r in records) * HOURS_PER_RECORD


def cooling_degree_hours(records: list[dict]) -> float:
    return sum(max(0.0, r["ambient_c"] - COOLING_BASE_C) for r in records) * HOURS_PER_RECORD


def demand_summary(summer: list[dict], winter: list[dict]) -> dict:
    records = summer + winter
    return {
        "heating_degree_hours": round(heating_degree_hours(records), 0),
        "cooling_degree_hours": round(cooling_degree_hours(records), 0),
        "winter_heating_degree_days": round(heating_degree_hours(winter) / HOURS_PER_DAY, 0),
        "winter_irradiation_kwh_per_m2": round(irradiation_kwh_per_m2(winter), 1),
    }


def surface_cooling(records: list[dict], city: City, albedo_before: float) -> list[float]:
    zone = ZoneInfo(city.timezone)
    deltas = []
    for record in records:
        if record["timestamp"].astimezone(zone).hour not in DAYTIME_LOCAL_HOURS:
            continue
        weather = Weather(record["ambient_c"], record["radiation_wm2"], record["wind_ms"])
        before = equilibrium_surface_temp(weather, albedo_before)
        deltas.append(before - equilibrium_surface_temp(weather, ASSUMED_COATED_ALBEDO))
    return deltas


def typical_roof_areas(rows: list[dict]) -> dict[str, float]:
    by_class: dict[str, list[float]] = {}
    for row in rows:
        by_class.setdefault(row["roof_class"], []).append(float(row["area_m2"]))
    return {roof_class: statistics.median(areas) for roof_class, areas in by_class.items()}


def city_comparison(city: City) -> dict:
    rows = roof_metrics(city)
    albedo_before = statistics.median(float(r["albedo"]) for r in rows)
    albedo_change = ASSUMED_COATED_ALBEDO - albedo_before
    summer, winter = season_weather(city, city.summer), season_weather(city, city.winter)
    primary = demand_weighted(summer + winter, albedo_change)
    cooling = surface_cooling(summer, city, albedo_before)
    return {
        "city": city.name,
        "summer_period": f"{city.summer[0]}..{city.summer[1]}",
        "winter_period": f"{city.winter[0]}..{city.winter[1]}",
        "roofs": len(rows),
        "median_current_albedo": round(albedo_before, 3),
        "coated_albedo": ASSUMED_COATED_ALBEDO,
        "heat_reference": heat_reference(city, max(r["ambient_c"] for r in summer)),
        "summer_surface_cooling_c": round(statistics.fmean(cooling), DECIMALS),
        "summer_peak_surface_cooling_c": round(max(cooling), DECIMALS),
        **demand_summary(summer, winter),
        "net_benefit_kwh_per_m2": primary["net_benefit_kwh_per_m2"],
        DEMAND_WEIGHTED: primary,
        SOLAR_ONLY: solar_only(summer, winter, albedo_change),
        "typical_roof_net_kwh": {
            roof_class: round(primary["net_benefit_kwh_per_m2"] * area, 0)
            for roof_class, area in typical_roof_areas(rows).items()
        },
    }


def build_report(cities: list[dict]) -> dict:
    return {
        "data_source": SIMULATED,
        "weather_source": "open-meteo hourly weather (real, third_party)",
        "generated_at": datetime.now().astimezone().isoformat(),
        "primary_method": DEMAND_WEIGHTED,
        "secondary_method": SOLAR_ONLY,
        "secondary_method_note": solar_only_note(cities),
        "methods": method_descriptions(),
        "cities": cities,
        "conclusion": build_conclusion(cities),
        "assumptions": list(ASSUMPTIONS),
        "method": method_descriptions()[DEMAND_WEIGHTED],
        "caveat": CAVEAT,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare seasonal cool-roof effects by city.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    report = build_report([city_comparison(city) for city in CITIES.values()])
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for city in report["cities"]:
        print(
            f"{city['city']}: {DEMAND_WEIGHTED} {city[DEMAND_WEIGHTED]}; "
            f"{SOLAR_ONLY} {city[SOLAR_ONLY]}; HDH {city['heating_degree_hours']}, "
            f"CDH {city['cooling_degree_hours']}; {city['heat_reference']['text']}"
        )
    print(report["secondary_method_note"])
    print(report["conclusion"])
    print(f"Written to {args.output}.")


if __name__ == "__main__":
    main()
