"""bulk_orders, bulk_order_lines

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulk_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("occasion", sa.String(length=30), nullable=False),
        sa.Column("event_at", sa.DateTime(), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=False),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lng", sa.Float(), nullable=True),
        sa.Column("gender_preference", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Float(), nullable=True),
        sa.Column("platform_fee", sa.Float(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("quoted_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("advance_amount", sa.Float(), nullable=True),
        sa.Column("advance_status", sa.String(length=20), nullable=True),
        sa.Column("advance_razorpay_order_id", sa.String(length=100), nullable=True),
        sa.Column("advance_razorpay_payment_id", sa.String(length=100), nullable=True),
        sa.Column("advance_razorpay_signature", sa.String(length=200), nullable=True),
        sa.Column("advance_paid_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_bulk_orders_consumer_id", "bulk_orders", ["consumer_id"])

    op.create_table(
        "bulk_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bulk_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bulk_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("design_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("designs.id"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reference_image_url", sa.String(length=500), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("unit_price_min", sa.Float(), nullable=False),
        sa.Column("unit_price_max", sa.Float(), nullable=False),
        sa.Column("unit_advance", sa.Float(), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=True),
    )
    op.create_index("ix_bulk_order_lines_bulk_order_id", "bulk_order_lines", ["bulk_order_id"])


def downgrade() -> None:
    op.drop_index("ix_bulk_order_lines_bulk_order_id", table_name="bulk_order_lines")
    op.drop_table("bulk_order_lines")
    op.drop_index("ix_bulk_orders_consumer_id", table_name="bulk_orders")
    op.drop_table("bulk_orders")
