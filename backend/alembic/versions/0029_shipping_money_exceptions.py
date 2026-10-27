"""shipping S2: COD remittance, failed-delivery (NDR) handling, return
condition

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHIPMENT_COLUMNS = (
    ("cod_remitted_at", sa.DateTime()),
    ("cod_remittance_ref", sa.String(80)),
    ("ndr_status", sa.String(12)),
    ("ndr_action", sa.String(20)),
    ("ndr_raised_at", sa.DateTime()),
    ("ndr_note", sa.String(300)),
)


def upgrade() -> None:
    for name, type_ in SHIPMENT_COLUMNS:
        op.add_column("shipments", sa.Column(name, type_, nullable=True))
    op.add_column("shipments", sa.Column("ndr_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("shop_orders", sa.Column("return_condition", sa.String(12), nullable=True))
    # Delivered COD orders already marked collected keep that status; from
    # now on "collected" means the courier has remitted the cash.
    op.execute("UPDATE shipments SET cod_remitted_at = delivered_at WHERE cod_amount > 0 AND delivered_at IS NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE shop_orders SET payment_status = 'cod_collected' WHERE payment_status = 'cod_with_courier'")
    op.drop_column("shop_orders", "return_condition")
    op.drop_column("shipments", "ndr_attempts")
    for name, _ in reversed(SHIPMENT_COLUMNS):
        op.drop_column("shipments", name)
