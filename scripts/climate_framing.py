"""Wording for the climate comparison: methods, assumptions and the presentation text.

The same weather gives opposite city rankings depending on whether all sunlight or only
demand-hour sunlight is counted, so the text states which framing is primary and why.
All numbers come from the computed cities and every comparative claim is checked against
them, so a rerun on other data cannot leave a stale sentence behind.
"""

from __future__ import annotations

from collections.abc import Sequence

from cities import City

DEMAND_WEIGHTED, SOLAR_ONLY = "demand_weighted", "solar_only"
# Standard degree-hour bases: UK/EU heating base 15.5 C, common cooling base 24 C.
HEATING_BASE_C = 15.5
COOLING_BASE_C = 24.0
# Historical peaks quoted next to the measured summer maximum, with their year, so an
# older record is never presented as this summer's value.
HISTORICAL_HEAT = {"london": "London reached 40 C in the July 2022 heatwave"}

ASSUMPTIONS = (
    "The share of kept-out sunlight that would have reached the building interior depends "
    "on insulation and roof build-up; for a well-insulated roof it is small, so the kWh/m2 "
    "figures are an upper bound on building energy.",
    "The summer gain is a real energy saving only in buildings that are actively cooled; in "
    "an unconditioned building it improves comfort but saves no energy.",
    f"Heating ({HEATING_BASE_C} C) and cooling ({COOLING_BASE_C} C) bases are standard "
    "degree-hour values, not fitted to these buildings.",
    "An hour counts as heating or cooling demand when it crosses a base; the kept-out "
    "sunlight of that hour is counted in full, not scaled by how far the base is crossed.",
)


def method_descriptions() -> dict[str, str]:
    return {
        DEMAND_WEIGHTED: (
            "Sunlight no longer absorbed = hourly global horizontal irradiation x (coated "
            "albedo - current median albedo), counted as benefit in hours above "
            f"{COOLING_BASE_C} C (cooling degree-hours) and as penalty in hours below "
            f"{HEATING_BASE_C} C (heating degree-hours), over summer and winter."
        ),
        SOLAR_ONLY: (
            "The same kept-out sunlight with all summer hours as benefit and all winter "
            "hours as penalty, regardless of heating or cooling demand."
        ),
    }


def heat_reference(city: City, summer_max_c: float) -> dict:
    year = int(city.summer[0][:4])
    text = (
        f"Hottest hour of summer {year} at the {city.name} reference point: "
        f"{summer_max_c:.1f} C (Open-Meteo)."
    )
    historical = HISTORICAL_HEAT.get(city.key)
    if historical:
        text += f" {historical}; that figure is from 2022, not {year}."
    return {
        "summer_max_ambient_c": round(summer_max_c, 1),
        "summer_year": year,
        "historical_peak": historical,
        "text": text,
    }


def _best_by(cities: Sequence[dict], method: str) -> dict:
    return max(cities, key=lambda city: city[method]["net_benefit_kwh_per_m2"])


def _net(city: dict, method: str) -> float:
    return city[method]["net_benefit_kwh_per_m2"]


def solar_only_note(cities: Sequence[dict]) -> str:
    """Why the secondary framing misleads: it charges every winter sun hour as a heating
    cost, so the sunnier winter looks worse even when no heat is needed in those hours."""
    sunny, dull = sorted(cities, key=lambda c: c["winter_irradiation_kwh_per_m2"], reverse=True)[:2]
    ratio = sunny["winter_irradiation_kwh_per_m2"] / dull["winter_irradiation_kwh_per_m2"]
    solar_best, demand_best = _best_by(cities, SOLAR_ONLY), _best_by(cities, DEMAND_WEIGHTED)
    agreement = (
        f"Same data, opposite conclusions: {SOLAR_ONLY} ranks {solar_best['city']} first on "
        f"net benefit, {DEMAND_WEIGHTED} ranks {demand_best['city']} first."
        if solar_best is not demand_best
        else f"Both framings rank {demand_best['city']} first on net benefit."
    )
    return (
        f"{SOLAR_ONLY} counts every hour of winter sun as a heating penalty, whether or not "
        f"the building needs heat then. {sunny['city']}'s winter sun is {ratio:.1f}x "
        f"{dull['city']}'s ({sunny['winter_irradiation_kwh_per_m2']} vs "
        f"{dull['winter_irradiation_kwh_per_m2']} kWh/m2), so this framing charges "
        f"{sunny['city']} a winter penalty of {sunny[SOLAR_ONLY]['heating_penalty_kwh_per_m2']} "
        f"vs {dull[SOLAR_ONLY]['heating_penalty_kwh_per_m2']} kWh/m2. {agreement} We use "
        f"{DEMAND_WEIGHTED} because kept-out sunlight only costs or saves energy in hours "
        "when the building needs heating or cooling."
    )


def _driver(cold: dict, warm: dict) -> str:
    cold_dw, warm_dw = cold[DEMAND_WEIGHTED], warm[DEMAND_WEIGHTED]
    benefit_gap = warm_dw["cooling_benefit_kwh_per_m2"] - cold_dw["cooling_benefit_kwh_per_m2"]
    penalty_gap = cold_dw["heating_penalty_kwh_per_m2"] - warm_dw["heating_penalty_kwh_per_m2"]
    if benefit_gap >= penalty_gap:
        text = (
            f"Most of the gap comes from fewer hours that need cooling in {cold['city']} "
            f"(cooling benefit {cold_dw['cooling_benefit_kwh_per_m2']} vs "
            f"{warm_dw['cooling_benefit_kwh_per_m2']} kWh/m2)."
        )
    else:
        text = (
            f"Most of the gap comes from the heating penalty "
            f"({cold_dw['heating_penalty_kwh_per_m2']} vs "
            f"{warm_dw['heating_penalty_kwh_per_m2']} kWh/m2)."
        )
    if penalty_gap <= 0:
        text += (
            f" {cold['city']}'s heating penalty is not larger than {warm['city']}'s, because "
            "its winter sun is weaker: there is less sunlight for the coating to reflect."
        )
    return text


def build_conclusion(cities: Sequence[dict]) -> str:
    by_need = sorted(cities, key=lambda city: city["heating_degree_hours"])
    warm, cold = by_need[0], by_need[-1]
    ratio = cold["heating_degree_hours"] / warm["heating_degree_hours"]
    cold_net, warm_net = _net(cold, DEMAND_WEIGHTED), _net(warm, DEMAND_WEIGHTED)
    comparison = "lower" if cold_net < warm_net else "not lower"
    return (
        f"Primary method ({DEMAND_WEIGHTED}): {cold['city']}'s heating need is {ratio:.1f}x "
        f"{warm['city']}'s ({cold['heating_degree_hours']:.0f} vs "
        f"{warm['heating_degree_hours']:.0f} heating degree-hours below {HEATING_BASE_C} C), "
        f"and the coating's net return there is {comparison}: {cold_net} vs {warm_net} kWh/m2 "
        f"of kept-out sunlight over the two seasons. {_driver(cold, warm)} "
        f"{cold['heat_reference']['text']}"
    )
