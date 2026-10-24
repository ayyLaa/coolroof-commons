from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WeatherRecord


def list_in_range(db: Session, roof_id: str, start: datetime, end: datetime) -> list[WeatherRecord]:
    query = (
        select(WeatherRecord)
        .where(
            WeatherRecord.roof_id == roof_id,
            WeatherRecord.timestamp >= start,
            WeatherRecord.timestamp <= end,
        )
        .order_by(WeatherRecord.timestamp)
    )
    return list(db.scalars(query))


def upsert_hourly(db: Session, roof_id: str, records: list[dict], overwrite: bool = True) -> None:
    """weather_records has no (roof_id, timestamp) unique constraint, so existing hours
    are matched here instead of with ON CONFLICT. overwrite=False only adds missing
    hours, leaving stored rows (e.g. demo seed weather) untouched."""
    if not records:
        return
    timestamps = [record["timestamp"] for record in records]
    existing = {
        row.timestamp: row for row in list_in_range(db, roof_id, min(timestamps), max(timestamps))
    }
    for record in records:
        row = existing.get(record["timestamp"])
        if row is None:
            db.add(WeatherRecord(roof_id=roof_id, **record))
            continue
        if not overwrite:
            continue
        for column, value in record.items():
            setattr(row, column, value)
    db.flush()
