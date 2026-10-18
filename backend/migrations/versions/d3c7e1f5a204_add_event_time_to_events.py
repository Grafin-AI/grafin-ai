"""add event_time to transaction_events

Revision ID: d3c7e1f5a204
Revises: b2f1a9c4d7e0
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3c7e1f5a204"
down_revision: Union[str, Sequence[str], None] = "b2f1a9c4d7e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable, backfill from the parent transaction, then enforce NOT NULL so the
    # migration is safe on a populated database.
    op.add_column(
        "transaction_events",
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE transaction_events te "
        "SET event_time = t.event_time "
        "FROM transactions t "
        "WHERE te.transaction_id = t.id"
    )
    op.alter_column("transaction_events", "event_time", nullable=False)
    op.create_index(
        "ix_transaction_events_event_time", "transaction_events", ["event_time"]
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_events_event_time", table_name="transaction_events")
    op.drop_column("transaction_events", "event_time")
