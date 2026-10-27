"""shipping: package sizes, shipments, tracking events, PIN-code cache,
courier webhook inbox

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
SIZE_COLUMNS = (("weight_g", sa.Integer()), ("length_cm", sa.Float()), ("breadth_cm", sa.Float()), ("height_cm", sa.Float()))


def upgrade() -> None:
    for table in ("shop_products", "shop_product_variants"):
        for name, type_ in SIZE_COLUMNS:
            op.add_column(table, sa.Column(name, type_, nullable=True))

    op.create_table(
        "shipments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID, sa.ForeignKey("shop_orders.id"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("awb", sa.String(80), nullable=True),
        sa.Column("courier_name", sa.String(80), nullable=True),
        sa.Column("tracking_url", sa.String(300), nullable=True),
        sa.Column("label_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="booked"),
        sa.Column("weight_g", sa.Integer(), nullable=False),
        sa.Column("length_cm", sa.Float(), nullable=False),
        sa.Column("breadth_cm", sa.Float(), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("cod_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("shipping_charge", sa.Float(), nullable=True),
        sa.Column("pickup_scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "awb", name="uq_shipments_provider_awb"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_status", "shipments", ["status"])

    op.create_table(
        "shipment_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_id", UUID, sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("location", sa.String(120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("shipment_id", "external_id", name="uq_shipment_events_external"),
    )
    op.create_index("ix_shipment_events_shipment_id", "shipment_events", ["shipment_id"])

    op.create_table(
        "pincode_serviceability",
        sa.Column("pincode", sa.String(6), primary_key=True),
        sa.Column("provider", sa.String(30), primary_key=True),
        sa.Column("deliverable", sa.Boolean(), nullable=False),
        sa.Column("cod_available", sa.Boolean(), nullable=False),
        sa.Column("eta_min_days", sa.Integer(), nullable=True),
        sa.Column("eta_max_days", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "shipping_webhook_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False, unique=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="received"),
        sa.Column("result", sa.String(160), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    # Orders already shipped by hand get a shipment record, so every order
    # reads its tracking from one place.
    op.execute("""
        INSERT INTO shipments (id, order_id, provider, awb, courier_name, tracking_url, status, weight_g, length_cm,
                               breadth_cm, height_cm, cod_amount, last_event_at, delivered_at, created_at, updated_at)
        SELECT gen_random_uuid(), id, 'manual', NULLIF(tracking_number, ''), courier_name, tracking_url,
               CASE WHEN status = 'delivered' THEN 'delivered' WHEN status = 'returned' THEN 'rto_delivered' ELSE 'in_transit' END,
               500, 15, 10, 5, CASE WHEN payment_method = 'cod' THEN total_amount ELSE 0 END,
               COALESCE(delivered_at, shipped_at), delivered_at, COALESCE(shipped_at, created_at), COALESCE(shipped_at, created_at)
        FROM shop_orders WHERE shipped_at IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("shipping_webhook_events")
    op.drop_table("pincode_serviceability")
    op.drop_table("shipment_events")
    op.drop_table("shipments")
    for table in ("shop_product_variants", "shop_products"):
        for name, _ in reversed(SIZE_COLUMNS):
            op.drop_column(table, name)
