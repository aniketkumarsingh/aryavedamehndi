"""DPDP consent fields for consumers (User table)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_given", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("consent_given_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consent_given_at")
    op.drop_column("users", "consent_given")
