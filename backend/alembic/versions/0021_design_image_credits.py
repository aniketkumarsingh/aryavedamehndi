"""designs.image_kind / image_credit, design_images.credit

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("designs", sa.Column("image_kind", sa.String(length=20), server_default="photo", nullable=False))
    op.add_column("designs", sa.Column("image_credit", postgresql.JSONB(), nullable=True))
    op.add_column("design_images", sa.Column("credit", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("design_images", "credit")
    op.drop_column("designs", "image_credit")
    op.drop_column("designs", "image_kind")
