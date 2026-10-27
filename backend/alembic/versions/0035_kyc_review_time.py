"""KYC review time (retention of rejected KYC documents)

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artist_profiles", sa.Column("kyc_reviewed_at", sa.DateTime(), nullable=True))
    # Already-reviewed artists: start the retention clock now.
    op.execute("UPDATE artist_profiles SET kyc_reviewed_at = now() at time zone 'utc' WHERE kyc_status IN ('approved', 'rejected')")


def downgrade() -> None:
    op.drop_column("artist_profiles", "kyc_reviewed_at")
