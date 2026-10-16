"""permanent address text for artist profile and extra locations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artist_profiles", sa.Column("address_text", sa.Text(), nullable=True))
    op.add_column("artist_locations", sa.Column("address_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("artist_locations", "address_text")
    op.drop_column("artist_profiles", "address_text")
