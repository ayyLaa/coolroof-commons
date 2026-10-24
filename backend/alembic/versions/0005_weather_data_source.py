"""weather record data_source

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21

Open-Meteo weather is neither our measurement nor our simulation (third_party); the demo
seed writes fabricated weather (simulated). Labelling each row keeps the two apart and
lets scripts/seed.py delete only the rows it created. Existing rows default to
third_party; the seed's own rows are relabelled on its next run.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "weather_records",
        sa.Column("data_source", sa.String(), nullable=False, server_default="third_party"),
    )
    op.create_check_constraint(
        "ck_weather_records_data_source",
        "weather_records",
        "data_source IN ('simulated', 'third_party')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_weather_records_data_source", "weather_records", type_="check")
    op.drop_column("weather_records", "data_source")
