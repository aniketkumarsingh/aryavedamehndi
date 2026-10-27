"""growth G3: referrals, wallet ledger, attribution, server-side conversions

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=True))
    op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])
    op.add_column("users", sa.Column("referred_by", UUID, sa.ForeignKey("users.id"), nullable=True))
    op.add_column("users", sa.Column("attribution", JSONB, nullable=True))
    op.add_column("users", sa.Column("analytics_consent", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "referrals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("referrer_id", UUID, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("referee_id", UUID, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("first_order_id", UUID, sa.ForeignKey("shop_orders.id"), nullable=True),
        sa.Column("reward_amount", sa.Float(), nullable=True),
        sa.Column("credited_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "wallet_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("remaining", sa.Float(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("order_id", UUID, sa.ForeignKey("shop_orders.id"), nullable=True),
        sa.Column("referral_id", UUID, sa.ForeignKey("referrals.id"), nullable=True),
        sa.Column("allocations", JSONB, nullable=True),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.add_column("shop_orders", sa.Column("referral_discount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("shop_orders", sa.Column("wallet_amount", sa.Float(), nullable=False, server_default="0"))
    op.add_column("shop_orders", sa.Column("attribution", JSONB, nullable=True))
    for table in ("bookings", "bulk_orders"):
        op.add_column(table, sa.Column("source", sa.String(40), nullable=True))
        op.add_column(table, sa.Column("attribution", JSONB, nullable=True))

    op.create_table(
        "conversion_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("event_name", sa.String(40), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_id", "platform", "event_name", name="uq_conversion_once"),
    )


def downgrade() -> None:
    op.drop_table("conversion_events")
    for table in ("bulk_orders", "bookings"):
        op.drop_column(table, "attribution")
        op.drop_column(table, "source")
    op.drop_column("shop_orders", "attribution")
    op.drop_column("shop_orders", "wallet_amount")
    op.drop_column("shop_orders", "referral_discount")
    op.drop_table("wallet_entries")
    op.drop_table("referrals")
    op.drop_column("users", "analytics_consent")
    op.drop_column("users", "attribution")
    op.drop_column("users", "referred_by")
    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_column("users", "referral_code")
