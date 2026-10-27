"""growth G2: product reviews and ratings, city/occasion landing pages

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "product_reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("product_id", UUID, sa.ForeignKey("shop_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", UUID, sa.ForeignKey("shop_orders.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("photo_urls", sa.Text(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("product_id", "user_id", name="uq_product_review_once"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_product_review_rating"),
    )
    op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"])
    op.add_column("shop_products", sa.Column("rating_avg", sa.Float(), nullable=False, server_default="0"))
    op.add_column("shop_products", sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "landing_pages",
        sa.Column("slug", sa.String(100), primary_key=True),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("heading", sa.String(150), nullable=False),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("city", sa.String(60), nullable=True),
        sa.Column("occasion", sa.String(30), nullable=True),
        sa.Column("meta_description", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("landing_pages")
    op.drop_column("shop_products", "rating_count")
    op.drop_column("shop_products", "rating_avg")
    op.drop_index("ix_product_reviews_product_id", table_name="product_reviews")
    op.drop_table("product_reviews")
