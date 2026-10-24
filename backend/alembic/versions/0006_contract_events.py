"""contract events

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-21

contract_states keeps only the latest state of each tranche; the oracle relays every
on-chain escrow event, and this table keeps them so the contract page can show the
timeline that led to that state.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contract_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("roof_id", sa.String(), sa.ForeignKey("roofs.id"), nullable=False),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("tranche", sa.String(), nullable=True),
        sa.Column("amount_wei", sa.String(), nullable=True),
        sa.Column("tx_hash", sa.String(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_contract_events_roof_id", "contract_events", ["roof_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_events_roof_id", table_name="contract_events")
    op.drop_table("contract_events")
