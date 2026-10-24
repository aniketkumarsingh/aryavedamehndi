"""full-resolution zoom copies: designs.image_hd_url, design_images.hd_url

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("designs", sa.Column("image_hd_url", sa.String(500), nullable=True))
    op.add_column("design_images", sa.Column("hd_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("design_images", "hd_url")
    op.drop_column("designs", "image_hd_url")
