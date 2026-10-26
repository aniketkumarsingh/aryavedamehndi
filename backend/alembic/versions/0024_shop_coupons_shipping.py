"""shop coupons, shipping fee, tracking, cancellation and refund fields

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_COLUMNS = (
    ("items_amount", sa.Float(), {}),
    ("discount_amount", sa.Float(), {"server_default": "0", "nullable": False}),
    ("shipping_fee", sa.Float(), {"server_default": "0", "nullable": False}),
    ("coupon_code", sa.String(length=40), {}),
    ("courier_name", sa.String(length=80), {}),
    ("tracking_number", sa.String(length=80), {}),
    ("tracking_url", sa.String(length=300), {}),
    ("cancelled_at", sa.DateTime(), {}),
    ("cancel_reason", sa.String(length=200), {}),
    ("refund_status", sa.String(length=20), {}),
    ("refund_id", sa.String(length=100), {}),
)


def upgrade() -> None:
    op.create_table(
        "shop_coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("discount_type", sa.String(length=10), nullable=False),
        sa.Column("discount_value", sa.Float(), nullable=False),
        sa.Column("max_discount", sa.Float(), nullable=True),
        sa.Column("min_order_amount", sa.Float(), server_default="0", nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for name, type_, kw in ORDER_COLUMNS:
        op.add_column("shop_orders", sa.Column(name, type_, nullable=kw.get("nullable", True), server_default=kw.get("server_default")))
    op.create_index("ix_shop_orders_coupon_code", "shop_orders", ["coupon_code"])
    # Older orders had no discount or shipping, so their items total is the order total.
    op.execute("UPDATE shop_orders SET items_amount = total_amount WHERE items_amount IS NULL")


def downgrade() -> None:
    op.drop_index("ix_shop_orders_coupon_code", table_name="shop_orders")
    for name, _, _ in reversed(ORDER_COLUMNS):
        op.drop_column("shop_orders", name)
    op.drop_table("shop_coupons")
