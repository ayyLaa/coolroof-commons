"""data_source labels on roofs and measurements

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21

Every surface temperature must say whether it was measured (satellite) or simulated
(physical model / demo seed). Existing rows default to simulated: only
scripts/fetch_satellite.py may promote a roof to measured.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

DATA_SOURCE_CHECK = "data_source IN ('measured', 'simulated')"


def upgrade() -> None:
    for table in ("roofs", "measurements"):
        op.add_column(
            table,
            sa.Column("data_source", sa.String(), nullable=False, server_default="simulated"),
        )
        op.create_check_constraint(f"ck_{table}_data_source", table, DATA_SOURCE_CHECK)


def downgrade() -> None:
    for table in ("roofs", "measurements"):
        op.drop_constraint(f"ck_{table}_data_source", table, type_="check")
        op.drop_column(table, "data_source")
