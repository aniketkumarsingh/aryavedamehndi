"""artist live location while en route

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("artist_current_lat", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("artist_current_lng", sa.Float(), nullable=True))
    op.add_column("bookings", sa.Column("artist_location_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "artist_location_updated_at")
    op.drop_column("bookings", "artist_current_lng")
    op.drop_column("bookings", "artist_current_lat")
