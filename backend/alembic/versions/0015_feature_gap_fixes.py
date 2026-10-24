"""check-in flag, dispute outcome, consumer ratings, advance credit,
platform settings, CMS history, refresh-token rotation

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("arrival_distance_m", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("arrival_flagged", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("bookings", sa.Column("dispute_outcome", sa.String(20), nullable=True))
    op.add_column("bookings", sa.Column("dispute_notes", sa.Text(), nullable=True))
    op.add_column("bookings", sa.Column("dispute_resolved_at", sa.DateTime(), nullable=True))

    op.add_column("users", sa.Column("consumer_rating_avg", sa.Float(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("consumer_rating_count", sa.Integer(), server_default="0", nullable=False))

    op.add_column("payments", sa.Column("advance_credit", sa.Float(), server_default="0", nullable=False))
    op.add_column("payments", sa.Column("platform_owes_artist", sa.Float(), server_default="0", nullable=False))

    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "cms_content_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("updated_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cms_content_versions_key", "cms_content_versions", ["key"])

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_cms_content_versions_key", table_name="cms_content_versions")
    op.drop_table("cms_content_versions")
    op.drop_table("platform_settings")
    op.drop_column("payments", "platform_owes_artist")
    op.drop_column("payments", "advance_credit")
    op.drop_column("users", "consumer_rating_count")
    op.drop_column("users", "consumer_rating_avg")
    op.drop_column("bookings", "dispute_resolved_at")
    op.drop_column("bookings", "dispute_notes")
    op.drop_column("bookings", "dispute_outcome")
    op.drop_column("bookings", "arrival_flagged")
    op.drop_column("bookings", "arrival_distance_m")
