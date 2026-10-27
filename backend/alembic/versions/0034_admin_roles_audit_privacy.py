"""platform P3: admin roles, audit log, order notes, account deletion

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("admin_role", sa.String(10), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    # Everyone who is an admin today keeps full access.
    op.execute("UPDATE users SET admin_role = 'owner' WHERE role = 'admin'")

    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("admin_id", UUID, sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("admin_role", sa.String(10), nullable=True),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("query", sa.String(500), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
    )
    op.create_table(
        "admin_notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID, nullable=False),
        sa.Column("author_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_notes_target", "admin_notes", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_notes_target", table_name="admin_notes")
    op.drop_table("admin_notes")
    op.drop_table("admin_audit_log")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "admin_role")
