"""CoolRoof Commons - removes structures that are not ordinary roofs from the large sets.

The large-roof sets keep any building inside an industrial area, which also catches
stadiums, sports halls and garages. Their surfaces (open stands, pitches, parking decks,
pool halls) heat differently from a warehouse roof, so they would blur the albedo
comparison. The rule reads each roof's own OSM tags from the city's Geofabrik extract:
- drop building types that are not a closed roof (stadium, grandstand, garage, ...),
- drop anything tagged leisure=* or amenity=parking,
- keep building=yes only when it lies inside a landuse=industrial area.
Roof ids are left untouched, so the existing satellite metrics stay valid; the excluded
ids are written to data/large_roof_exclusions.json and scripts/satellite_evidence.py
reads them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from cities import CITIES, LARGE_ROOF_EXCLUSIONS_PATH, City, buildings_path  # noqa: E402
from fetch_buildings import EXTRACT, LARGE, read_extract, widest_bbox  # noqa: E402

NON_ROOF_BUILDING_TYPES = ("stadium", "grandstand", "garage", "garages", "parking", "carport")
GENERIC_BUILDING = "yes"
PARKING = "parking"
INDUSTRIAL = "industrial"
RULE = (
    "Excluded: building in "
    f"{', '.join(NON_ROOF_BUILDING_TYPES)}; any leisure=* tag; amenity=parking; "
    "building=yes outside a landuse=industrial area."
)


def exclusion_reason(tags: dict[str, str | None], inside_industrial: bool) -> str | None:
    """None means the structure counts as an ordinary roof and stays in the set."""
    building = tags.get("building")
    if building in NON_ROOF_BUILDING_TYPES:
        return f"building={building}"
    if tags.get("leisure"):
        return f"leisure={tags['leisure']}"
    if tags.get("amenity") == PARKING:
        return f"amenity={PARKING}"
    if building == GENERIC_BUILDING and not inside_industrial:
        return "building=yes outside landuse=industrial"
    return None


def industrial_flags(buildings: gpd.GeoDataFrame, features: gpd.GeoDataFrame) -> list[bool]:
    areas = features[(features["landuse"] == INDUSTRIAL) & features["building"].isna()]
    if areas.empty:
        return [False] * len(buildings)
    points = buildings.geometry.representative_point()
    return list(points.within(areas.union_all()))


def osm_tags(features: gpd.GeoDataFrame) -> dict[str, dict[str, str | None]]:
    """Roofs missing from the extract get empty tags: nothing in OSM says to drop them."""
    columns = ("building", "leisure", "amenity")
    tagged = features[features["building"].notna()]
    return {
        row["osm_id"]: {key: row[key] if pd.notna(row[key]) else None for key in columns}
        for _, row in tagged.iterrows()
    }


def city_exclusions(city: City) -> dict:
    roofs = gpd.read_file(buildings_path(city, LARGE))
    features = read_extract(city.osm_extract, widest_bbox(city.industrial_bbox))
    tags_by_osm_id = osm_tags(features)
    excluded = []
    for roof, inside in zip(roofs.itertuples(), industrial_flags(roofs, features)):
        tags = tags_by_osm_id.get(roof.osm_id, {"building": roof.building})
        reason = exclusion_reason(tags, inside)
        if reason is not None:
            excluded.append({"roof_id": roof.roof_id, "osm_id": roof.osm_id, "reason": reason})
    return {
        "n_before": len(roofs),
        "n_excluded": len(excluded),
        "n_after": len(roofs) - len(excluded),
        "excluded": excluded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Exclude non-roof structures from large sets.")
    parser.add_argument("--output", type=Path, default=LARGE_ROOF_EXCLUSIONS_PATH)
    args = parser.parse_args()
    cities = {key: city_exclusions(city) for key, city in CITIES.items()}
    report = {"rule": RULE, "osm_source": EXTRACT, "cities": cities}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, result in cities.items():
        print(f"{key}: {result['n_before']} -> {result['n_after']} large roofs.")
        for item in result["excluded"]:
            print(f"  {item['roof_id']} {item['osm_id']}: {item['reason']}")
    print(f"Written to {args.output}.")


if __name__ == "__main__":
    main()
