"""Pilot city definitions shared by every data script.

The scripts are parametric: adding a city means adding an entry here, not a pipeline.
Athens and London are deliberately contrasting climates: Athens is hot all summer with
mild winters, London is usually cool, reached 40 C in the July 2022 heatwave and has a
real heating season, so a reflective roof's winter cost matters there.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_DIR = REPO_ROOT / "data" / "cache" / "geofabrik"
# Written by scripts/clean_large_roofs.py, read by scripts/satellite_evidence.py.
LARGE_ROOF_EXCLUSIONS_PATH = REPO_ROOT / "data" / "large_roof_exclusions.json"

Bbox = tuple[float, float, float, float]  # (west, south, east, north)


@dataclass(frozen=True)
class City:
    key: str
    name: str
    roof_id_prefix: str
    timezone: str
    # Nominatim boundary for the residential (small) set when fetched from Overpass.
    residential_place: str
    residential_bbox: Bbox
    industrial_bbox: Bbox
    # Geofabrik extract, the offline alternative to the public Overpass server.
    osm_extract: Path
    summer: tuple[str, str]
    winter: tuple[str, str]

    @property
    def summer_end_exclusive(self) -> str:
        """Earth Engine filterDate treats its end as exclusive."""
        return (date.fromisoformat(self.summer[1]) + timedelta(days=1)).isoformat()


CITIES = {
    "athens": City(
        key="athens",
        name="Athens",
        roof_id_prefix="ATH",
        timezone="Europe/Athens",
        residential_place="Municipality of Vyronas, Attica, Greece",
        residential_bbox=(23.745, 37.945, 23.785, 37.965),
        # Piraeus port (Perama, Keratsini, Drapetsona) and the western industrial belt.
        industrial_bbox=(23.58, 37.925, 23.70, 37.995),
        osm_extract=EXTRACT_DIR / "greece-latest.osm.pbf",
        summer=("2026-06-01", "2026-08-31"),
        winter=("2025-12-01", "2026-02-28"),
    ),
    "london": City(
        key="london",
        name="London",
        roof_id_prefix="LON",
        timezone="Europe/London",
        residential_place="London Borough of Hackney, London, England",
        # Hackney / Stoke Newington terraces.
        residential_bbox=(-0.085, 51.540, -0.040, 51.565),
        # Park Royal, London's largest industrial estate.
        industrial_bbox=(-0.290, 51.515, -0.235, 51.545),
        osm_extract=EXTRACT_DIR / "greater-london-latest.osm.pbf",
        summer=("2026-06-01", "2026-08-31"),
        winter=("2025-12-01", "2026-02-28"),
    ),
}
DEFAULT_CITY = "athens"


def add_city_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--city", choices=CITIES, default=DEFAULT_CITY, help="Pilot city.")


def buildings_path(city: City, roof_class: str) -> Path:
    suffix = "" if roof_class == "small" else f"_{roof_class}"
    return REPO_ROOT / "data" / f"buildings_{city.key}{suffix}.geojson"


def metrics_path(city: City, roof_class: str) -> Path:
    return REPO_ROOT / "data" / f"satellite_metrics_{city.key}_{roof_class}.csv"
