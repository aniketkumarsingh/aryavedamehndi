"""artist KYC docs, extra locations, booking settlement mode

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artist_profiles", sa.Column("aadhaar_number", sa.String(20), nullable=True))
    op.add_column("artist_profiles", sa.Column("aadhaar_doc_url", sa.String(500), nullable=True))
    op.add_column("artist_profiles", sa.Column("pan_number", sa.String(15), nullable=True))
    op.add_column("artist_profiles", sa.Column("pan_doc_url", sa.String(500), nullable=True))

    op.add_column("bookings", sa.Column("settlement_mode", sa.String(20), nullable=True))
    op.add_column("bookings", sa.Column("settlement_recorded_at", sa.DateTime(), nullable=True))

    op.create_table(
        "artist_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artist_profiles.user_id"), nullable=False),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("artist_locations")
    op.drop_column("bookings", "settlement_recorded_at")
    op.drop_column("bookings", "settlement_mode")
    op.drop_column("artist_profiles", "pan_doc_url")
    op.drop_column("artist_profiles", "pan_number")
    op.drop_column("artist_profiles", "aadhaar_doc_url")
    op.drop_column("artist_profiles", "aadhaar_number")
