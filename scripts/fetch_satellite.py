"""CoolRoof Commons - derives roof surface temperature and albedo from satellite imagery.

Measured before-values exist for only a handful of roofs, so prioritisation needs a
city-wide estimate. Two thermal instruments are queried because their pixel size decides
whether a roof is resolved at all:
- Landsat 8/9 ST_B10: 100 m native (distributed resampled to 30 m), overpass ~11:45 local.
- ECOSTRESS L2T LSTE: 70 m native, irregular ISS overpass times.
Every row records the instrument and its native resolution. Earth Engine is slow and
quota-bound, so results are cached per roof set in data/satellite_metrics_<set>.csv and
reused until --refresh is passed. The original data/roof_metrics.csv is left untouched.
Cities, seasons and file names come from scripts/cities.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ee  # noqa: E402
from google.auth.exceptions import GoogleAuthError  # noqa: E402

from app.core.exceptions import RoofNotFoundError  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import MEASURED, Roof  # noqa: E402
from cities import CITIES, City, add_city_argument, buildings_path, metrics_path  # noqa: E402
from ml.scoring import RoofMetrics, ScoredRoof, compute_priority_scores  # noqa: E402

ROOF_SETS = ("small", "large")
METRIC_FIELDS = (
    "roof_id",
    "roof_class",
    "area_m2",
    "albedo",
    "albedo_instrument",
    "albedo_resolution_m",
    "instrument",
    "instrument_resolution_m",
    "surface_temp_c",
)
# tileScale trades speed for memory so 300 polygons fit within EE's per-tile limits.
TILE_SCALE = 4
KELVIN_TO_CELSIUS_OFFSET = 273.15

LANDSAT_COLLECTIONS = ("LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2")
# Distributed grid used for the zonal mean; the thermal band's native resolution is 100 m.
LANDSAT_SCALE_M = 30
LANDSAT_TIRS_RESOLUTION_M = 100
ST_B10_SCALE = 0.00341802
ST_B10_OFFSET_K = 149.0
# QA_PIXEL bits: 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow.
LANDSAT_CLOUD_QA_BITS = (1, 2, 3, 4)

ECOSTRESS_COLLECTION = "NASA/ECOSTRESS/L2T_LSTE/V2"
ECOSTRESS_RESOLUTION_M = 70
# The ISS overpasses at any hour. Only 10:00-15:59 local time is kept, around Landsat's
# late-morning overpass: at night albedo has no effect, and mixing night scenes into the
# median would wash out the very contrast being measured.
ECOSTRESS_LOCAL_HOURS = (10, 15)
# QC bits 0-1: 0 best quality, 1 nominal; 2 and 3 mean cloud-affected or not produced.
ECOSTRESS_QC_QUALITY_BITS = 0b11
ECOSTRESS_MAX_QC_QUALITY = 1

SENTINEL2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
SENTINEL2_SCALE_M = 10
# B11/B12 enter the albedo at 20 m, so that is the albedo's effective resolution.
ALBEDO_RESOLUTION_M = 20
ALBEDO_INSTRUMENT = "Sentinel-2 L2A, Liang (2001) broadband albedo"
SENTINEL2_REFLECTANCE_SCALE = 1e-4
# Scenes this cloudy rarely contribute clear pixels and only slow the median down.
SENTINEL2_MAX_SCENE_CLOUD_PCT = 20
# Scene classification classes to drop: 3 cloud shadow, 8/9 cloud, 10 cirrus.
SENTINEL2_MASKED_SCL_CLASSES = (3, 8, 9, 10)

# Shortwave broadband albedo, Liang (2001) narrow-to-broadband conversion:
#   albedo = 0.356*blue + 0.130*red + 0.373*nir + 0.085*swir1 + 0.072*swir2 - 0.0018
# Source: Liang, S. (2001). Narrowband to broadband conversions of land surface albedo I:
# Algorithms. Remote Sensing of Environment, 76(2), 213-238.
# https://doi.org/10.1016/S0034-4257(00)00205-4
# The coefficients were fitted for Landsat TM/ETM+ bands 1, 3, 4, 5, 7; applying them to
# the spectrally matching Sentinel-2 bands B2, B4, B8, B11, B12 is a common approximation.
LIANG_COEFFICIENTS = {"B2": 0.356, "B4": 0.130, "B8": 0.373, "B11": 0.085, "B12": 0.072}
LIANG_INTERCEPT = -0.0018

TEMP_DECIMALS = 2
ALBEDO_DECIMALS = 3
PRIORITY_DECIMALS = 3


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    resolution_m: int
    scale_m: int
    build: Callable[[ee.Geometry, City], ee.ImageCollection]


def initialize_earth_engine(project: str | None) -> None:
    try:
        ee.Authenticate()
        ee.Initialize(project=project)
    except (ee.EEException, GoogleAuthError) as error:
        raise SystemExit(
            "Earth Engine initialisation failed. Run `earthengine authenticate`, make sure "
            "the Google Cloud project is registered for Earth Engine with the API enabled, "
            f"and pass it via --project or the EE_PROJECT env var. Details: {error}"
        ) from error


def load_buildings(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/fetch_buildings.py first.")
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def to_feature_collection(buildings: list[dict]) -> ee.FeatureCollection:
    features = [
        ee.Feature(
            ee.Geometry(building["geometry"]), {"roof_id": building["properties"]["roof_id"]}
        )
        for building in buildings
    ]
    return ee.FeatureCollection(features)


def mask_landsat_clouds(image: ee.Image) -> ee.Image:
    cloud_bits = sum(1 << bit for bit in LANDSAT_CLOUD_QA_BITS)
    clear = image.select("QA_PIXEL").bitwiseAnd(cloud_bits).eq(0)
    return image.updateMask(clear)


def landsat_surface_temp_c(image: ee.Image) -> ee.Image:
    kelvin = image.select("ST_B10").multiply(ST_B10_SCALE).add(ST_B10_OFFSET_K)
    return kelvin.subtract(KELVIN_TO_CELSIUS_OFFSET).rename("surface_temp_c")


def summer_window(city: City) -> tuple[str, str]:
    return city.summer[0], city.summer_end_exclusive


def build_landsat_lst(region: ee.Geometry, city: City) -> ee.ImageCollection:
    merged = ee.ImageCollection(LANDSAT_COLLECTIONS[0]).merge(
        ee.ImageCollection(LANDSAT_COLLECTIONS[1])
    )
    filtered = merged.filterBounds(region).filterDate(*summer_window(city))
    return filtered.map(mask_landsat_clouds).map(landsat_surface_temp_c)


def mask_ecostress(image: ee.Image) -> ee.Image:
    quality = image.select("QC").bitwiseAnd(ECOSTRESS_QC_QUALITY_BITS)
    clear = (
        image.select("cloud")
        .eq(0)
        .And(image.select("water").eq(0))
        .And(quality.lte(ECOSTRESS_MAX_QC_QUALITY))
    )
    return image.updateMask(clear)


def ecostress_surface_temp_c(image: ee.Image) -> ee.Image:
    """L2T LST is delivered in kelvin."""
    return image.select("LST").subtract(KELVIN_TO_CELSIUS_OFFSET).rename("surface_temp_c")


def utc_hours(city: City, local_hours: tuple[int, int]) -> tuple[int, int]:
    """Earth Engine filters acquisition hours in UTC; the offset is taken at the start of
    summer, which covers the whole season because no DST change falls inside it."""
    start = datetime.fromisoformat(city.summer[0]).replace(tzinfo=ZoneInfo(city.timezone))
    offset_h = int(start.utcoffset().total_seconds() // 3600)
    return local_hours[0] - offset_h, local_hours[1] - offset_h


def build_ecostress_lst(region: ee.Geometry, city: City) -> ee.ImageCollection:
    first_hour, last_hour = utc_hours(city, ECOSTRESS_LOCAL_HOURS)
    filtered = (
        ee.ImageCollection(ECOSTRESS_COLLECTION)
        .filterBounds(region)
        .filterDate(*summer_window(city))
        .filter(ee.Filter.calendarRange(first_hour, last_hour, "hour"))
    )
    return filtered.map(mask_ecostress).map(ecostress_surface_temp_c)


INSTRUMENTS = {
    "landsat": Instrument(
        "landsat",
        "Landsat 8/9 C2L2 ST_B10",
        LANDSAT_TIRS_RESOLUTION_M,
        LANDSAT_SCALE_M,
        build_landsat_lst,
    ),
    "ecostress": Instrument(
        "ecostress",
        "ECOSTRESS L2T LSTE V2",
        ECOSTRESS_RESOLUTION_M,
        ECOSTRESS_RESOLUTION_M,
        build_ecostress_lst,
    ),
}
# Database surface temperatures come from one instrument for every roof, so priority
# scores never compare values from instruments with different footprints.
PRIMARY_INSTRUMENT = "landsat"


def mask_sentinel_clouds(image: ee.Image) -> ee.Image:
    scl = image.select("SCL")
    clear = ee.Image(1)
    for scl_class in SENTINEL2_MASKED_SCL_CLASSES:
        clear = clear.And(scl.neq(scl_class))
    return image.updateMask(clear)


def liang_albedo(image: ee.Image) -> ee.Image:
    reflectance = image.select(list(LIANG_COEFFICIENTS)).multiply(SENTINEL2_REFLECTANCE_SCALE)
    weighted = reflectance.multiply(ee.Image.constant(list(LIANG_COEFFICIENTS.values())))
    albedo = weighted.reduce(ee.Reducer.sum()).add(LIANG_INTERCEPT)
    return albedo.clamp(0, 1).rename("albedo")


def build_albedo_image(region: ee.Geometry, city: City) -> ee.ImageCollection:
    filtered = (
        ee.ImageCollection(SENTINEL2_COLLECTION)
        .filterBounds(region)
        .filterDate(*summer_window(city))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", SENTINEL2_MAX_SCENE_CLOUD_PCT))
    )
    return filtered.map(mask_sentinel_clouds).map(liang_albedo)


def zonal_mean(
    collection: ee.ImageCollection, roofs: ee.FeatureCollection, scale_m: int, label: str
) -> dict[str, float | None]:
    """Fails loudly on an empty collection; a median of nothing would silently yield
    an image without bands and every roof would come back as missing."""
    scene_count = collection.size().getInfo()
    if scene_count == 0:
        raise SystemExit(f"No {label} scenes found in the city's summer window.")
    print(f"{label}: median of {scene_count} scenes.")
    reduced = collection.median().reduceRegions(
        collection=roofs, reducer=ee.Reducer.mean(), scale=scale_m, tileScale=TILE_SCALE
    )
    features = reduced.select(["roof_id", "mean"], None, False).getInfo()["features"]
    return {f["properties"]["roof_id"]: f["properties"].get("mean") for f in features}


def round_or_none(value: float | None, decimals: int) -> float | None:
    return None if value is None else round(value, decimals)


def metric_row(
    feature: dict, roof_class: str, albedo: float | None, instrument: Instrument, temp: float | None
) -> dict:
    properties = feature["properties"]
    return {
        "roof_id": properties["roof_id"],
        "roof_class": roof_class,
        "area_m2": properties["area_m2"],
        "albedo": round_or_none(albedo, ALBEDO_DECIMALS),
        "albedo_instrument": ALBEDO_INSTRUMENT,
        "albedo_resolution_m": ALBEDO_RESOLUTION_M,
        "instrument": instrument.name,
        "instrument_resolution_m": instrument.resolution_m,
        "surface_temp_c": round_or_none(temp, TEMP_DECIMALS),
    }


def compute_roof_metrics(
    buildings: list[dict], roof_class: str, instruments: list[Instrument], city: City
) -> list[dict]:
    """One row per roof and thermal instrument; albedo is shared by all of a roof's rows."""
    roofs = to_feature_collection(buildings)
    region = roofs.geometry().bounds()
    albedo_images = build_albedo_image(region, city)
    albedos = zonal_mean(albedo_images, roofs, SENTINEL2_SCALE_M, "Sentinel-2 albedo")
    rows = []
    for instrument in instruments:
        images = instrument.build(region, city)
        temps = zonal_mean(images, roofs, instrument.scale_m, instrument.name)
        for feature in buildings:
            roof_id = feature["properties"]["roof_id"]
            albedo, temp = albedos.get(roof_id), temps.get(roof_id)
            rows.append(metric_row(feature, roof_class, albedo, instrument, temp))
    return rows


def write_metrics_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_metrics_csv(path: Path, instrument: Instrument) -> list[RoofMetrics]:
    """Rows with a missing metric are skipped: a roof without a satellite estimate cannot
    be ranked fairly against roofs that have one."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["instrument"] == instrument.name]
    return [
        RoofMetrics(
            roof_id=row["roof_id"],
            area_m2=float(row["area_m2"]),
            albedo=float(row["albedo"]),
            surface_temp_c=float(row["surface_temp_c"]),
        )
        for row in rows
        if row["albedo"] and row["surface_temp_c"]
    ]


def write_roof_metrics(
    metrics: list[RoofMetrics], scores: list[ScoredRoof], instrument: Instrument
) -> None:
    score_by_id = {score.roof_id: score.priority_score for score in scores}
    with SessionLocal() as session:
        for metric in metrics:
            roof = session.get(Roof, metric.roof_id)
            if roof is None:
                raise RoofNotFoundError(metric.roof_id)
            roof.albedo = metric.albedo
            roof.surface_temp_c = metric.surface_temp_c
            roof.surface_temp_instrument = instrument.name
            roof.surface_temp_resolution_m = instrument.resolution_m
            roof.priority_score = round(score_by_id[metric.roof_id], PRIORITY_DECIMALS)
            roof.data_source = MEASURED
        session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch satellite roof metrics via Earth Engine.")
    parser.add_argument("--set", choices=ROOF_SETS, default="small", dest="roof_set")
    add_city_argument(parser)
    parser.add_argument(
        "--instruments", default="landsat,ecostress", help=f"Comma list of {list(INSTRUMENTS)}."
    )
    parser.add_argument(
        "--project", default=os.getenv("EE_PROJECT"), help="Earth Engine Cloud project."
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore the cached CSV.")
    parser.add_argument("--skip-db", action="store_true", help="Only write the CSV file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    instruments = [INSTRUMENTS[key] for key in args.instruments.split(",")]
    city = CITIES[args.city]
    path = metrics_path(city, args.roof_set)
    if args.refresh or not path.exists():
        initialize_earth_engine(args.project)
        buildings = load_buildings(buildings_path(city, args.roof_set))
        rows = compute_roof_metrics(buildings, args.roof_set, instruments, city)
        write_metrics_csv(rows, path)
        print(f"Metrics written to {path}.")
    else:
        print(f"Using cached {path}; pass --refresh to query Earth Engine again.")

    primary = INSTRUMENTS[PRIMARY_INSTRUMENT]
    metrics = read_metrics_csv(path, primary)
    print(f"{len(metrics)} roofs have both {primary.name} temperature and albedo.")
    if not args.skip_db:
        write_roof_metrics(metrics, compute_priority_scores(metrics), primary)
        print(f"{len(metrics)} roofs updated with albedo, surface_temp_c and priority_score.")


if __name__ == "__main__":
    main()
