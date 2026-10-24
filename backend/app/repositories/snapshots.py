from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Roof, WeatherRecord

WGS84_SRID = 4326


def list_roofs_with_geojson(db: Session) -> list[tuple[Roof, float, float, str]]:
    """Full GeoJSON precision: the snapshot is a backup, not an API response."""
    centroid = func.ST_Centroid(Roof.geom)
    query = select(
        Roof, func.ST_Y(centroid), func.ST_X(centroid), func.ST_AsGeoJSON(Roof.geom)
    ).order_by(Roof.id)
    return [tuple(row) for row in db.execute(query)]


def list_weather(
    db: Session, roof_ids: Sequence[str], data_source: str
) -> list[WeatherRecord]:
    query = (
        select(WeatherRecord)
        .where(WeatherRecord.roof_id.in_(roof_ids), WeatherRecord.data_source == data_source)
        .order_by(WeatherRecord.roof_id, WeatherRecord.timestamp)
    )
    return list(db.scalars(query))


def insert_missing_roofs(db: Session, roofs: Sequence[dict]) -> int:
    """Existing roofs are left as they are, so a restart never overwrites newer data.
    Each roof's "geometry" is a GeoJSON string."""
    if not roofs:
        return 0
    values = [
        {
            **{key: value for key, value in roof.items() if key != "geometry"},
            "geom": func.ST_SetSRID(func.ST_GeomFromGeoJSON(roof["geometry"]), WGS84_SRID),
        }
        for roof in roofs
    ]
    result = db.execute(insert(Roof).values(values).on_conflict_do_nothing(index_elements=["id"]))
    db.flush()
    return result.rowcount
