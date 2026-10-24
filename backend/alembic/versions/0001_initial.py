"""initial schema: roofs, measurements, verifications, weather_records, contract_states

Revision ID: 0001
Revises:
Create Date: 2026-10-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "roofs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("geom", Geometry(geometry_type="POLYGON", srid=4326), nullable=True),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("albedo", sa.Float(), nullable=False),
        sa.Column("surface_temp_c", sa.Float(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "measurements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roof_id", sa.String(), sa.ForeignKey("roofs.id"), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("raw_readings", JSONB(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("normalized_delta_c", sa.Float(), nullable=True),
        sa.Column("anomaly_flags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("photo_path", sa.String(), nullable=True),
        sa.Column("coverage_pct", sa.Float(), nullable=True),
    )

    op.create_table(
        "verifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roof_id", sa.String(), sa.ForeignKey("roofs.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("evidence_hash", sa.String(), nullable=False),
        sa.Column("device_signature", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "weather_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roof_id", sa.String(), sa.ForeignKey("roofs.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ambient_c", sa.Float(), nullable=False),
        sa.Column("radiation_wm2", sa.Float(), nullable=False),
        sa.Column("wind_ms", sa.Float(), nullable=False),
        sa.Column("max_gust_ms", sa.Float(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=False),
    )

    op.create_table(
        "contract_states",
        sa.Column("roof_id", sa.String(), sa.ForeignKey("roofs.id"), primary_key=True),
        sa.Column("tranche_name", sa.String(), primary_key=True),
        sa.Column("pct", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tx_hash", sa.String(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("contract_states")
    op.drop_table("weather_records")
    op.drop_table("verifications")
    op.drop_table("measurements")
    op.drop_table("roofs")
