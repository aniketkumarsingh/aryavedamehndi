"""designs.style / coverage / occasions / photo_needed

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("designs", sa.Column("style", sa.String(length=30), nullable=True))
    op.add_column("designs", sa.Column("coverage", sa.String(length=30), nullable=True))
    op.add_column("designs", sa.Column("occasions", postgresql.ARRAY(sa.String(length=30)), server_default="{}", nullable=False))
    op.add_column("designs", sa.Column("photo_needed", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("designs", "photo_needed")
    op.drop_column("designs", "occasions")
    op.drop_column("designs", "coverage")
    op.drop_column("designs", "style")
