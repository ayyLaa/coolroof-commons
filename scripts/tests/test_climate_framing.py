from cities import CITIES
from climate_framing import (
    DEMAND_WEIGHTED,
    SOLAR_ONLY,
    build_conclusion,
    heat_reference,
    solar_only_note,
)


def balance(benefit: float, penalty: float) -> dict:
    return {
        "cooling_benefit_kwh_per_m2": benefit,
        "heating_penalty_kwh_per_m2": penalty,
        "net_benefit_kwh_per_m2": round(benefit - penalty, 1),
    }


def city(name: str, hdh: float, winter_sun: float, demand: dict, solar: dict) -> dict:
    key = name.lower()
    return {
        "city": name,
        "heating_degree_hours": hdh,
        "winter_irradiation_kwh_per_m2": winter_sun,
        "heat_reference": heat_reference(CITIES[key], 36.0 if key == "london" else 39.0),
        DEMAND_WEIGHTED: demand,
        SOLAR_ONLY: solar,
    }


ATHENS = city("Athens", 9270, 237.1, balance(322.9, 82.1), balance(327.5, 111.7))
LONDON = city("London", 19188, 85.2, balance(180.1, 65.0), balance(344.6, 52.2))


def test_conclusion_states_heating_need_and_lower_net_without_larger_penalty() -> None:
    text = build_conclusion([ATHENS, LONDON])

    assert "London's heating need is 2.1x Athens's" in text
    assert "net return there is lower: 115.1 vs 240.8" in text
    assert "fewer hours that need cooling" in text
    assert "heating penalty is not larger" in text


def test_secondary_note_explains_opposite_rankings() -> None:
    note = solar_only_note([ATHENS, LONDON])

    assert "2.8x" in note
    assert "solar_only ranks London first" in note
    assert "demand_weighted ranks Athens first" in note


def test_secondary_note_admits_when_framings_agree() -> None:
    agreeing = {**LONDON, SOLAR_ONLY: balance(200.0, 60.0)}

    assert "Both framings rank Athens first" in solar_only_note([ATHENS, agreeing])


def test_heat_reference_separates_2026_from_2022() -> None:
    london = heat_reference(CITIES["london"], 36.0)

    assert london["summer_year"] == 2026
    assert "summer 2026" in london["text"] and "36.0 C" in london["text"]
    assert "from 2022, not 2026" in london["text"]
    assert heat_reference(CITIES["athens"], 39.0)["historical_peak"] is None


def test_higher_net_in_colder_city_is_not_reported_as_lower() -> None:
    generous_london = {**LONDON, DEMAND_WEIGHTED: balance(400.0, 65.0)}

    assert "net return there is not lower" in build_conclusion([ATHENS, generous_london])
