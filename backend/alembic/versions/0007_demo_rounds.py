"""demo rounds

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22

Each escrow tranche pays once per project, so every demo round funds fresh projects on
chain ("ATH-0142#3"). demo_rounds records the rounds started; the latest is current.
contract_events.round keeps which round an event came from, so a replayed event from an
earlier round cannot overwrite the current round's state.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "demo_rounds",
        sa.Column("round", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column(
        "contract_events",
        sa.Column("round", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("contract_events", "round")
    op.drop_table("demo_rounds")
