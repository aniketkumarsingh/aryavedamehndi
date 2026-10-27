"""growth G1: marketing consent, server carts, personal coupons, order
source, occasion campaigns, artist slug + city

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("users", sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("marketing_opt_in_at", sa.DateTime(), nullable=True))
    op.create_table(
        "consent_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])

    op.create_table(
        "carts",
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("items", JSONB, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("reminder_stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminded_at", sa.DateTime(), nullable=True),
        sa.Column("coupon_code", sa.String(40), nullable=True),
    )
    op.add_column("shop_coupons", sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("shop_orders", sa.Column("source", sa.String(40), nullable=True))

    op.create_table(
        "occasions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("occasion_date", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "campaign_sends",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("occasion_id", UUID, sa.ForeignKey("occasions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channels", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("occasion_id", "user_id", name="uq_campaign_send"),
    )

    op.add_column("artist_profiles", sa.Column("slug", sa.String(90), nullable=True))
    op.add_column("artist_profiles", sa.Column("city", sa.String(60), nullable=True))
    op.execute("""
        UPDATE artist_profiles a SET slug = trim(both '-' from lower(regexp_replace(coalesce(u.name, 'artist'), '[^a-zA-Z0-9]+', '-', 'g')))
                                             || '-' || substr(a.user_id::text, 1, 6)
        FROM users u WHERE u.id = a.user_id
    """)
    op.create_unique_constraint("uq_artist_profiles_slug", "artist_profiles", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_artist_profiles_slug", "artist_profiles", type_="unique")
    op.drop_column("artist_profiles", "city")
    op.drop_column("artist_profiles", "slug")
    op.drop_table("campaign_sends")
    op.drop_table("occasions")
    op.drop_column("shop_orders", "source")
    op.drop_column("shop_coupons", "user_id")
    op.drop_table("carts")
    op.drop_index("ix_consent_records_user_id", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_column("users", "marketing_opt_in_at")
    op.drop_column("users", "marketing_opt_in")
