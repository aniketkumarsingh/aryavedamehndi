"""design catalog: designs, artist_designs, bookings.design_id

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-19

Also turns every existing package sample image into its own catalog
design (package price band and duration), so no sample is lost.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    designs = op.create_table(
        "designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("price_min", sa.Float(), nullable=False),
        sa.Column("price_max", sa.Float(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_designs_package_id", "designs", ["package_id"])

    op.create_table(
        "artist_designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artist_profiles.user_id"), nullable=False),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id"), nullable=False),
        sa.Column("proof_image_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("artist_id", "design_id", name="uq_artist_design"),
    )
    op.create_index("ix_artist_designs_artist_id", "artist_designs", ["artist_id"])
    op.create_index("ix_artist_designs_design_id", "artist_designs", ["design_id"])

    op.add_column("bookings", sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id"), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name, price_min, price_max, duration_minutes, sample_image_urls, is_active FROM packages")
    ).fetchall()
    seeded = []
    for pkg in rows:
        urls = [u for u in (pkg.sample_image_urls or "").split(",") if u]
        for i, url in enumerate(urls, start=1):
            seeded.append(
                {
                    "id": uuid.uuid4(),
                    "package_id": pkg.id,
                    "name": f"{pkg.name} - Design {i}",
                    "image_url": url,
                    "price_min": pkg.price_min,
                    "price_max": pkg.price_max,
                    "duration_minutes": pkg.duration_minutes,
                    "sort_order": i,
                    "is_active": pkg.is_active,
                }
            )
    if seeded:
        op.bulk_insert(designs, seeded)


def downgrade() -> None:
    op.drop_column("bookings", "design_id")
    op.drop_index("ix_artist_designs_design_id", table_name="artist_designs")
    op.drop_index("ix_artist_designs_artist_id", table_name="artist_designs")
    op.drop_table("artist_designs")
    op.drop_index("ix_designs_package_id", table_name="designs")
    op.drop_table("designs")
