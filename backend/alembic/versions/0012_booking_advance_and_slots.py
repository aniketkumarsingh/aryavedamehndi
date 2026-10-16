"""package advance amount, booking advance payment + availability slot link

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("packages", sa.Column("advance_amount", sa.Float(), server_default="0", nullable=False))

    op.add_column(
        "bookings",
        sa.Column("availability_slot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artist_availability.id"), nullable=True),
    )
    op.add_column("bookings", sa.Column("advance_amount", sa.Float(), server_default="0", nullable=False))
    op.add_column("bookings", sa.Column("advance_status", sa.String(20), server_default="not_required", nullable=False))
    op.add_column("bookings", sa.Column("advance_razorpay_order_id", sa.String(100), nullable=True))
    op.add_column("bookings", sa.Column("advance_razorpay_payment_id", sa.String(100), nullable=True))
    op.add_column("bookings", sa.Column("advance_razorpay_signature", sa.String(200), nullable=True))
    op.add_column("bookings", sa.Column("advance_paid_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "advance_paid_at")
    op.drop_column("bookings", "advance_razorpay_signature")
    op.drop_column("bookings", "advance_razorpay_payment_id")
    op.drop_column("bookings", "advance_razorpay_order_id")
    op.drop_column("bookings", "advance_status")
    op.drop_column("bookings", "advance_amount")
    op.drop_column("bookings", "availability_slot_id")
    op.drop_column("packages", "advance_amount")
