"""shop invoices: HSN/GST per product and order line, invoice numbers,
shipping state and PIN code

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("shop_products", "shop_order_items"):
        op.add_column(table, sa.Column("hsn_code", sa.String(length=8), nullable=True))
        op.add_column(table, sa.Column("gst_rate", sa.Float(), nullable=True))
    op.add_column("shop_orders", sa.Column("invoice_number", sa.String(length=16), nullable=True))
    op.create_unique_constraint("uq_shop_orders_invoice_number", "shop_orders", ["invoice_number"])
    op.add_column("shop_orders", sa.Column("shipping_state", sa.String(length=60), nullable=True))
    op.add_column("shop_orders", sa.Column("shipping_pincode", sa.String(length=6), nullable=True))
    op.create_table(
        "shop_invoice_counters",
        sa.Column("financial_year", sa.String(length=4), primary_key=True),  # "2627" = Apr 2026 - Mar 2027
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("shop_invoice_counters")
    op.drop_column("shop_orders", "shipping_pincode")
    op.drop_column("shop_orders", "shipping_state")
    op.drop_constraint("uq_shop_orders_invoice_number", "shop_orders", type_="unique")
    op.drop_column("shop_orders", "invoice_number")
    for table in ("shop_order_items", "shop_products"):
        op.drop_column(table, "gst_rate")
        op.drop_column(table, "hsn_code")
