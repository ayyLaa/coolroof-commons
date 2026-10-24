"""roof timezone

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21

Normalisation needs each reading's local hour. Timestamps stay UTC; every roof gets
the IANA timezone of its location, backfilled from the geometry centroid.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from timezonefinder import TimezoneFinder

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("roofs", sa.Column("timezone", sa.String(), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, ST_Y(ST_Centroid(geom)), ST_X(ST_Centroid(geom)) FROM roofs")
    ).all()
    finder = TimezoneFinder()
    for roof_id, lat, lon in rows:
        name = finder.timezone_at(lat=lat, lng=lon) if lat is not None else None
        if name is None:
            raise RuntimeError(f"Cannot determine a timezone for roof {roof_id}.")
        connection.execute(
            sa.text("UPDATE roofs SET timezone = :tz WHERE id = :id"), {"tz": name, "id": roof_id}
        )
    op.alter_column("roofs", "timezone", nullable=False)


def downgrade() -> None:
    op.drop_column("roofs", "timezone")
