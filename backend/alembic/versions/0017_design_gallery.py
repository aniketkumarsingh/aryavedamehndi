"""design gallery: design_images, designs.image_source

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("designs", sa.Column("image_source", sa.String(200), nullable=True))
    op.create_table(
        "design_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="photo"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_key", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_design_images_design_id", "design_images", ["design_id"])


def downgrade() -> None:
    op.drop_index("ix_design_images_design_id", table_name="design_images")
    op.drop_table("design_images")
    op.drop_column("designs", "image_source")
