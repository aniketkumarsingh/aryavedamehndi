"""consumer profile fields, masked calling, Razorpay Route escrow fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Consumer profile
    op.add_column("users", sa.Column("guardian_name", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("secondary_phone", sa.String(15), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("anniversary_date", sa.Date(), nullable=True))

    # Razorpay Route linked account for artist payouts
    op.add_column("artist_profiles", sa.Column("razorpay_linked_account_id", sa.String(60), nullable=True))

    # Masked calling
    op.add_column("bookings", sa.Column("masked_call_number", sa.String(20), nullable=True))
    op.add_column("bookings", sa.Column("masked_call_provider_ref", sa.String(100), nullable=True))

    # Payment escrow/split fields
    op.add_column("payments", sa.Column("is_full_escrow", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("payments", sa.Column("artist_share", sa.Float(), nullable=True))
    op.add_column("payments", sa.Column("platform_share", sa.Float(), nullable=True))
    op.add_column("payments", sa.Column("payout_status", sa.String(20), server_default="not_applicable", nullable=False))
    op.add_column("payments", sa.Column("razorpay_transfer_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "razorpay_transfer_id")
    op.drop_column("payments", "payout_status")
    op.drop_column("payments", "platform_share")
    op.drop_column("payments", "artist_share")
    op.drop_column("payments", "is_full_escrow")

    op.drop_column("bookings", "masked_call_provider_ref")
    op.drop_column("bookings", "masked_call_number")

    op.drop_column("artist_profiles", "razorpay_linked_account_id")

    op.drop_column("users", "anniversary_date")
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "secondary_phone")
    op.drop_column("users", "guardian_name")
