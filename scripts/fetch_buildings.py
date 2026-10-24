"""CoolRoof Commons - pulls real building footprints for Athens from OSM.

Two sets:
- small: a residential district (Vyronas) with typical ~180 m2 roofs.
- large: warehouses and industrial halls around Piraeus and the western industrial belt,
  >= 2000 m2. Landsat's thermal pixel is 100 m (10 000 m2), so only roofs of this size
  have a chance of dominating the pixel that measures them.
The priority_score written here is a temporary area-based placeholder;
scripts/fetch_satellite.py replaces it with the real score.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import geopandas as gpd  # noqa: E402
import osmium  # noqa: E402
import osmium.filter  # noqa: E402
import osmium.geom  # noqa: E402
import osmnx as ox  # noqa: E402
import pandas as pd  # noqa: E402
from osmnx._errors import ResponseStatusCodeError  # noqa: E402
from geoalchemy2.elements import WKTElement  # noqa: E402
from shapely import wkb  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402

from app.core.timezones import timezone_for  # noqa: E402
from cities import CITIES, Bbox, City, add_city_argument, buildings_path  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Roof  # noqa: E402

OSMNX_CACHE_DIR = REPO_ROOT / "data" / "cache" / "osmnx"
# The extract is the offline alternative to Overpass, which asks automated users to
# avoid its public server; per-city files are listed in scripts/cities.py.
OVERPASS, EXTRACT = "overpass", "extract"
# The public Overpass server is often saturated; a bbox query over the industrial belt
# can take minutes, well beyond osmnx's default timeout.
OVERPASS_TIMEOUT_S = 900
# The Overpass usage policy asks clients to identify themselves.
OVERPASS_USER_AGENT = "CoolRoofCommons/0.1 (hackathon research script; low-volume building queries)"
# When the server is at capacity it answers 502/504 and asks for exponential backoff.
OVERPASS_RETRY_DELAYS_S = (30, 60, 120, 240)
WGS84 = "EPSG:4326"
WGS84_SRID = 4326

MIN_AREA_M2 = 50.0
MAX_AREA_M2 = 5000.0
MAX_BUILDINGS = 300
SAMPLE_RANDOM_STATE = 42

LARGE_BUILDING_TYPES = ("warehouse", "industrial", "retail", "commercial", "hangar")
LARGE_MIN_AREA_M2 = 2000.0
LARGE_MIN_COUNT = 60
BBOX_GROWTH_DEG = 0.03
MAX_BBOX_EXPANSIONS = 3

SMALL, LARGE = "small", "large"
INITIAL_STATUS = "candidate"
# No measurement exists yet for OSM roofs; these stand in until a before-measurement is taken.
PLACEHOLDER_ALBEDO = 0.15
PLACEHOLDER_SURFACE_TEMP_C = 55.0
PRIORITY_DECIMALS = 3
AREA_DECIMALS = 1


@dataclass(frozen=True)
class BuildingSet:
    roof_class: str
    # Seed roofs live in XXX-0xxx, small OSM roofs in XXX-1xxx, large ones in XXX-2xxx.
    roof_id_offset: int
    min_area_m2: float
    max_area_m2: float | None


BUILDING_SETS = {
    SMALL: BuildingSet(SMALL, 1000, MIN_AREA_M2, MAX_AREA_M2),
    LARGE: BuildingSet(LARGE, 2000, LARGE_MIN_AREA_M2, None),
}


def to_footprints(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    polygons = features[(features.geometry.geom_type == "Polygon") & features["building"].notna()]
    osm_ids = [f"{element}/{osm_id}" for element, osm_id in polygons.index]
    return gpd.GeoDataFrame(
        {"osm_id": osm_ids, "building": polygons["building"].to_numpy()},
        geometry=polygons.geometry.to_numpy(),
        crs=polygons.crs,
    ).to_crs(WGS84)


def fetch_small_footprints(city: City, source: str) -> gpd.GeoDataFrame:
    if source == EXTRACT:
        return buildings_from_extract(read_extract(city.osm_extract, city.residential_bbox))
    return to_footprints(ox.features_from_place(city.residential_place, tags={"building": True}))


def with_overpass_backoff(query: Callable[[], gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    for delay_s in OVERPASS_RETRY_DELAYS_S:
        try:
            return query()
        except ResponseStatusCodeError as error:
            print(f"Overpass busy ({str(error)[:60]}...); retrying in {delay_s} s.")
            time.sleep(delay_s)
    return query()


def fetch_industrial_footprints(bbox: Bbox) -> gpd.GeoDataFrame:
    """Buildings tagged with a large-building type, plus any building inside a
    landuse=industrial area: many industrial halls are tagged only building=yes. The
    second query is limited to the industrial areas rather than every building in the
    bbox, which keeps the load on the public Overpass server small."""
    tags = {"building": list(LARGE_BUILDING_TYPES), "landuse": "industrial"}
    features = with_overpass_backoff(lambda: ox.features_from_bbox(bbox, tags=tags))
    for column in ("building", "landuse"):
        if column not in features:
            features = features.assign(**{column: None})
    areas = features[(features["landuse"] == "industrial") & features["building"].isna()]
    footprints = [to_footprints(features)]
    if not areas.empty:
        area_union = areas.to_crs(WGS84).union_all()
        inside = with_overpass_backoff(
            lambda: ox.features_from_polygon(area_union, tags={"building": True})
        )
        footprints.append(to_footprints(inside))
    combined = pd.concat(footprints, ignore_index=True).drop_duplicates("osm_id")
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=WGS84)


def expand_bbox(bbox: Bbox) -> Bbox:
    west, south, east, north = bbox
    return (
        west - BBOX_GROWTH_DEG,
        south - BBOX_GROWTH_DEG,
        east + BBOX_GROWTH_DEG,
        north + BBOX_GROWTH_DEG,
    )


def widest_bbox(bbox: Bbox) -> Bbox:
    for _ in range(MAX_BBOX_EXPANSIONS):
        bbox = expand_bbox(bbox)
    return bbox


def _first_location(area: osmium.osm.Area) -> tuple[float, float] | None:
    """None for areas without a usable outer ring (incomplete or broken OSM mapping)."""
    for ring in area.outer_rings():
        for node in ring:
            if node.location.valid():
                return node.lon, node.lat
    return None


def _inside(point: tuple[float, float] | None, bbox: Bbox) -> bool:
    if point is None:
        return False
    west, south, east, north = bbox
    return west <= point[0] <= east and south <= point[1] <= north


def _area_row(area: osmium.osm.Area, factory: osmium.geom.WKBFactory) -> dict | None:
    """Returns None for OSM areas whose rings cannot be assembled; broken mapping is
    skipped rather than repaired."""
    try:
        geometry = wkb.loads(factory.create_multipolygon(area), hex=True)
    except RuntimeError:
        return None
    if len(geometry.geoms) == 1:
        geometry = geometry.geoms[0]
    element = "way" if area.from_way() else "relation"
    return {
        "osm_id": f"{element}/{area.orig_id()}",
        "building": area.tags.get("building"),
        "landuse": area.tags.get("landuse"),
        "leisure": area.tags.get("leisure"),
        "amenity": area.tags.get("amenity"),
        "geometry": geometry,
    }


def read_extract(path: Path, bbox: Bbox) -> gpd.GeoDataFrame:
    """All buildings and landuse=industrial areas in bbox, read once from the extract."""
    if not path.exists():
        raise SystemExit(f"{path} not found; download it from download.geofabrik.de first.")
    processor = (
        osmium.FileProcessor(str(path))
        .with_areas()
        .with_filter(osmium.filter.EntityFilter(osmium.osm.AREA))
        .with_filter(osmium.filter.KeyFilter("building", "landuse"))
    )
    factory, rows = osmium.geom.WKBFactory(), []
    for area in processor:
        relevant = "building" in area.tags or area.tags.get("landuse") == "industrial"
        if relevant and _inside(_first_location(area), bbox):
            row = _area_row(area, factory)
            if row is not None:
                rows.append(row)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)


def buildings_from_extract(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Every building polygon; the residential set keeps all building types."""
    buildings = features[features["building"].notna() & (features.geometry.geom_type == "Polygon")]
    return buildings[["osm_id", "building", "geometry"]].reset_index(drop=True)


def industrial_from_extract(features: gpd.GeoDataFrame, bbox: Bbox) -> gpd.GeoDataFrame:
    """Same rule as the Overpass path: a large-building type, or inside an industrial area."""
    west, south, east, north = bbox
    in_bbox = features.cx[west:east, south:north]
    areas = in_bbox[(in_bbox["landuse"] == "industrial") & in_bbox["building"].isna()]
    buildings = in_bbox[in_bbox["building"].notna() & (in_bbox.geometry.geom_type == "Polygon")]
    typed = buildings["building"].isin(LARGE_BUILDING_TYPES)
    inside = (
        buildings.geometry.representative_point().within(areas.union_all())
        if not areas.empty
        else False
    )
    selected = buildings[typed | inside]
    return selected[["osm_id", "building", "geometry"]].reset_index(drop=True)


def fetch_large_footprints(building_set: BuildingSet, source: str, city: City) -> gpd.GeoDataFrame:
    """Widens the bbox until enough large roofs are found or the expansion budget ends;
    the albedo quartile comparison needs both tails reasonably populated."""
    bbox = city.industrial_bbox
    extract = read_extract(city.osm_extract, widest_bbox(bbox)) if source == EXTRACT else None
    for attempt in range(MAX_BBOX_EXPANSIONS + 1):
        if extract is None:
            candidates = fetch_industrial_footprints(bbox)
        else:
            candidates = industrial_from_extract(extract, bbox)
        footprints = add_area_m2(candidates)
        large_count = int((footprints["area_m2"] >= building_set.min_area_m2).sum())
        print(f"bbox {bbox}: {large_count} buildings >= {building_set.min_area_m2:.0f} m2.")
        if large_count >= LARGE_MIN_COUNT or attempt == MAX_BBOX_EXPANSIONS:
            break
        bbox = expand_bbox(bbox)
    return footprints


def add_area_m2(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Area must be measured in a metric CRS; degrees would give meaningless numbers."""
    projected = buildings.to_crs(buildings.estimate_utm_crs())
    return buildings.assign(area_m2=projected.area.round(AREA_DECIMALS).to_numpy())


def filter_by_area(buildings: gpd.GeoDataFrame, building_set: BuildingSet) -> gpd.GeoDataFrame:
    in_range = buildings["area_m2"] >= building_set.min_area_m2
    if building_set.max_area_m2 is not None:
        in_range &= buildings["area_m2"] <= building_set.max_area_m2
    return buildings[in_range]


def select_demo_sample(buildings: gpd.GeoDataFrame, limit: int) -> gpd.GeoDataFrame:
    """A seeded random sample spreads roofs over the area instead of clustering them,
    and sorting by osm_id keeps the assigned roof ids stable across reruns."""
    if len(buildings) > limit:
        buildings = buildings.sample(n=limit, random_state=SAMPLE_RANDOM_STATE)
    return buildings.sort_values("osm_id").reset_index(drop=True)


def compute_area_priority(area_m2: float) -> float:
    span = MAX_AREA_M2 - MIN_AREA_M2
    return round(min(1.0, (area_m2 - MIN_AREA_M2) / span), PRIORITY_DECIMALS)


def format_roof_id(index: int, offset: int, prefix: str) -> str:
    return f"{prefix}-{offset + index:04d}"


def assign_roof_fields(
    buildings: gpd.GeoDataFrame, building_set: BuildingSet, city: City
) -> gpd.GeoDataFrame:
    offset, prefix = building_set.roof_id_offset, city.roof_id_prefix
    return buildings.assign(
        roof_id=[format_roof_id(i, offset, prefix) for i in range(len(buildings))],
        priority_score=buildings["area_m2"].map(compute_area_priority),
        roof_class=building_set.roof_class,
    )


def save_geojson(buildings: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buildings.to_file(path, driver="GeoJSON")


def build_roof(
    roof_id: str,
    geometry: BaseGeometry,
    area_m2: float,
    priority: float,
    roof_class: str,
    city: City,
) -> Roof:
    centroid = geometry.centroid
    return Roof(
        id=roof_id,
        city=city.name,
        geom=WKTElement(geometry.wkt, srid=WGS84_SRID),
        area_m2=float(area_m2),
        albedo=PLACEHOLDER_ALBEDO,
        surface_temp_c=PLACEHOLDER_SURFACE_TEMP_C,
        priority_score=float(priority),
        status=INITIAL_STATUS,
        timezone=timezone_for(centroid.y, centroid.x),
        roof_class=roof_class,
    )


def write_roofs(buildings: gpd.GeoDataFrame, city: City) -> None:
    """merge() upserts by primary key, so rerunning the script refreshes rows instead of failing."""
    with SessionLocal() as session:
        for row in buildings.itertuples():
            roof = build_roof(
                row.roof_id, row.geometry, row.area_m2, row.priority_score, row.roof_class, city
            )
            session.merge(roof)
        session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch OSM building footprints for Athens.")
    parser.add_argument("--set", choices=BUILDING_SETS, default=SMALL, dest="building_set")
    add_city_argument(parser)
    parser.add_argument(
        "--source",
        choices=(OVERPASS, EXTRACT),
        default=OVERPASS,
        help="Live Overpass queries or the city's local Geofabrik extract.",
    )
    parser.add_argument("--limit", type=int, default=MAX_BUILDINGS, help="Maximum building count.")
    parser.add_argument("--skip-db", action="store_true", help="Only write the GeoJSON file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ox.settings.cache_folder = OSMNX_CACHE_DIR
    ox.settings.requests_timeout = OVERPASS_TIMEOUT_S
    ox.settings.http_user_agent = OVERPASS_USER_AGENT
    building_set, city = BUILDING_SETS[args.building_set], CITIES[args.city]
    if building_set.roof_class == LARGE:
        footprints = fetch_large_footprints(building_set, args.source, city)
    else:
        footprints = add_area_m2(fetch_small_footprints(city, args.source))
    selected = select_demo_sample(filter_by_area(footprints, building_set), args.limit)
    buildings = assign_roof_fields(selected, building_set, city)
    print(f"{len(footprints)} polygons fetched, {len(buildings)} {building_set.roof_class} kept.")

    output_path = buildings_path(city, building_set.roof_class)
    save_geojson(buildings, output_path)
    print(f"GeoJSON written to {output_path}.")

    if not args.skip_db:
        write_roofs(buildings, city)
        print(f"{len(buildings)} roofs upserted into the roofs table.")


if __name__ == "__main__":
    main()
