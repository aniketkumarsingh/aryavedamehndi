"""rate limit counters

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("window_start", sa.DateTime(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
