import json
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Roof

# 7 decimal degrees is about 1 cm on the ground, far below footprint accuracy; more
# digits would only grow the response.
GEOJSON_DECIMALS = 7


@dataclass(frozen=True)
class RoofWithLocation:
    roof: Roof
    lat: float
    lon: float
    geometry: dict | None = None


def _with_centroid(include_geometry: bool) -> Select:
    centroid = func.ST_Centroid(Roof.geom)
    columns = [Roof, func.ST_Y(centroid), func.ST_X(centroid)]
    if include_geometry:
        columns.append(func.ST_AsGeoJSON(Roof.geom, GEOJSON_DECIMALS))
    return select(*columns).where(Roof.geom.isnot(None))


def _to_located(row: tuple) -> RoofWithLocation:
    roof, lat, lon, *geojson = row
    geometry = json.loads(geojson[0]) if geojson else None
    return RoofWithLocation(roof=roof, lat=lat, lon=lon, geometry=geometry)


def get_roof(db: Session, roof_id: str) -> RoofWithLocation | None:
    row = db.execute(_with_centroid(include_geometry=True).where(Roof.id == roof_id)).first()
    return None if row is None else _to_located(row)


def list_roofs(
    db: Session,
    city: str | None,
    min_score: float | None,
    page: tuple[int, int],
    include_geometry: bool,
) -> list[RoofWithLocation]:
    """page is (limit, offset); the id tie-break keeps the order stable across pages."""
    limit, offset = page
    query = _with_centroid(include_geometry)
    if city is not None:
        query = query.where(func.lower(Roof.city) == city.lower())
    if min_score is not None:
        query = query.where(Roof.priority_score >= min_score)
    query = query.order_by(Roof.priority_score.desc(), Roof.id).limit(limit).offset(offset)
    return [_to_located(row) for row in db.execute(query)]
