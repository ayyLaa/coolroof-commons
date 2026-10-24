"""roof class and surface temperature instrument

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21

Roofs are now fetched in two classes (small residential, large industrial) because the
satellite's thermal pixel size decides whether a roof can be resolved at all. Each
surface temperature also records the instrument and its native resolution.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "roofs", sa.Column("roof_class", sa.String(), nullable=False, server_default="small")
    )
    op.create_check_constraint("ck_roofs_roof_class", "roofs", "roof_class IN ('small', 'large')")
    op.add_column("roofs", sa.Column("surface_temp_instrument", sa.String(), nullable=True))
    op.add_column("roofs", sa.Column("surface_temp_resolution_m", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("roofs", "surface_temp_resolution_m")
    op.drop_column("roofs", "surface_temp_instrument")
    op.drop_constraint("ck_roofs_roof_class", "roofs", type_="check")
    op.drop_column("roofs", "roof_class")
