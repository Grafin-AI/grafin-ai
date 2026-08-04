"""drop sim_state

Revision ID: b2f1a9c4d7e0
Revises: c105fac3e957
Create Date: 2026-06-25

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f1a9c4d7e0"
down_revision: Union[str, Sequence[str], None] = "c105fac3e957"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("sim_state")


def downgrade() -> None:
    op.create_table(
        "sim_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sim_now", sa.DateTime(timezone=True), nullable=False),
        sa.Column("speed", sa.Numeric(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("running", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("id = 1", name="sim_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
