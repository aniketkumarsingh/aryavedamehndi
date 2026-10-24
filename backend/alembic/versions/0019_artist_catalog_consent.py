"""artist_designs.catalog_consent

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artist_designs", sa.Column("catalog_consent", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("artist_designs", "catalog_consent")
