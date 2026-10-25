"""shop catalogue: product details, licence, variants

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shop_products", sa.Column("slug", sa.String(length=80), nullable=True))
    op.create_unique_constraint("uq_shop_products_slug", "shop_products", ["slug"])
    op.add_column("shop_products", sa.Column("category", sa.String(length=30), nullable=True))
    op.add_column("shop_products", sa.Column("ingredients", sa.Text(), nullable=True))
    op.add_column("shop_products", sa.Column("how_to_use", sa.Text(), nullable=True))
    op.add_column("shop_products", sa.Column("safety_notes", sa.Text(), nullable=True))
    op.add_column("shop_products", sa.Column("shelf_life", sa.String(length=120), nullable=True))
    op.add_column("shop_products", sa.Column("storage", sa.String(length=200), nullable=True))
    op.add_column("shop_products", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("shop_products", sa.Column("requires_licence", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("shop_products", sa.Column("licence_number", sa.String(length=80), nullable=True))
    op.add_column("shop_products", sa.Column("image_kind", sa.String(length=20), server_default="photo", nullable=False))
    op.add_column("shop_products", sa.Column("image_source", sa.String(length=200), nullable=True))
    op.create_table(
        "shop_product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shop_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_shop_product_variants_product_id", "shop_product_variants", ["product_id"])
    op.add_column("shop_order_items", sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shop_product_variants.id"), nullable=True))
    op.add_column("shop_order_items", sa.Column("variant_label", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("shop_order_items", "variant_label")
    op.drop_column("shop_order_items", "variant_id")
    op.drop_index("ix_shop_product_variants_product_id", table_name="shop_product_variants")
    op.drop_table("shop_product_variants")
    for col in ("image_source", "image_kind", "licence_number", "requires_licence", "sort_order", "storage", "shelf_life",
                "safety_notes", "how_to_use", "ingredients", "category"):
        op.drop_column("shop_products", col)
    op.drop_constraint("uq_shop_products_slug", "shop_products", type_="unique")
    op.drop_column("shop_products", "slug")
