"""shipping S3: return requests, reverse pickups, bulk-order shipments,
manual refunds, artist on-time alerts

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("shop_products", sa.Column("returnable", sa.Boolean(), nullable=False, server_default=sa.true()))
    # Henna, hair and skin products: returns only if damaged or wrong (refund policy).
    op.execute("UPDATE shop_products SET returnable = false WHERE category IN ('body-art', 'hair', 'skin')")

    op.add_column("refunds", sa.Column("method", sa.String(20), nullable=False, server_default="razorpay"))
    op.add_column("refunds", sa.Column("reference", sa.String(100), nullable=True))

    op.create_table(
        "return_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID, sa.ForeignKey("shop_orders.id"), nullable=False),
        sa.Column("consumer_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("reason_code", sa.String(20), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("photo_urls", sa.Text(), nullable=True),
        sa.Column("items", JSONB, nullable=False),
        sa.Column("refund_amount", sa.Float(), nullable=False),
        sa.Column("refund_upi", sa.String(100), nullable=True),
        sa.Column("condition", sa.String(12), nullable=True),
        sa.Column("admin_note", sa.String(300), nullable=True),
        sa.Column("refund_id", UUID, sa.ForeignKey("refunds.id"), nullable=True),
        sa.Column("decided_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_return_requests_order_id", "return_requests", ["order_id"])
    op.create_index("ix_return_requests_status", "return_requests", ["status"])

    op.alter_column("shipments", "order_id", nullable=True)
    op.add_column("shipments", sa.Column("bulk_order_id", UUID, sa.ForeignKey("bulk_orders.id"), nullable=True))
    op.add_column("shipments", sa.Column("direction", sa.String(8), nullable=False, server_default="forward"))
    op.add_column("shipments", sa.Column("return_request_id", UUID, sa.ForeignKey("return_requests.id"), nullable=True))
    op.add_column("shipments", sa.Column("description", sa.String(200), nullable=True))
    op.create_index("ix_shipments_bulk_order_id", "shipments", ["bulk_order_id"])
    op.create_check_constraint("ck_shipments_has_order", "shipments", "order_id IS NOT NULL OR bulk_order_id IS NOT NULL")

    op.add_column("bookings", sa.Column("artist_reminded_at", sa.DateTime(), nullable=True))
    op.add_column("bookings", sa.Column("sla_alerted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "sla_alerted_at")
    op.drop_column("bookings", "artist_reminded_at")
    op.drop_constraint("ck_shipments_has_order", "shipments", type_="check")
    op.drop_index("ix_shipments_bulk_order_id", table_name="shipments")
    for name in ("description", "return_request_id", "direction", "bulk_order_id"):
        op.drop_column("shipments", name)
    op.execute("DELETE FROM shipments WHERE order_id IS NULL")
    op.alter_column("shipments", "order_id", nullable=False)
    op.drop_table("return_requests")
    op.drop_column("refunds", "reference")
    op.drop_column("refunds", "method")
    op.drop_column("shop_products", "returnable")
