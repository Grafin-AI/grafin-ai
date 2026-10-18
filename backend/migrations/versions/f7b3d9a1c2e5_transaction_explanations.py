"""persisted transaction explanations

Revision ID: f7b3d9a1c2e5
Revises: e4a8b2c6d913
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7b3d9a1c2e5"
down_revision: Union[str, Sequence[str], None] = "e4a8b2c6d913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_explanations",
        sa.Column(
            "transaction_id", sa.BigInteger(), sa.ForeignKey("transactions.id"),
            primary_key=True, autoincrement=False,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("pattern_matching", sa.Text(), nullable=False),
        sa.Column("behavior_analysis", sa.Text(), nullable=False),
        sa.Column("network_analysis", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.String(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("references", postgresql.JSONB(), nullable=False),
        sa.Column("risk_factors", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("str_draft", postgresql.JSONB(), nullable=True),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("str_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("transaction_explanations")
