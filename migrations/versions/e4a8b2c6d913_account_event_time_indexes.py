"""composite (account, event_time) indexes on transactions

Revision ID: e4a8b2c6d913
Revises: d3c7e1f5a204
"""
from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "e4a8b2c6d913"
down_revision: Union[str, Sequence[str], None] = "d3c7e1f5a204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Explanation evidence windows: WHERE {from,to}_account = :a AND event_time BETWEEN.
    # The single-column account indexes alone force a heap filter on event_time.
    op.create_index(
        "ix_transactions_from_account_event_time",
        "transactions", ["from_account", "event_time"],
    )
    op.create_index(
        "ix_transactions_to_account_event_time",
        "transactions", ["to_account", "event_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_to_account_event_time", table_name="transactions")
    op.drop_index("ix_transactions_from_account_event_time", table_name="transactions")
