import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.core.time import utcnow


class ShopProduct(Base):
    __tablename__ = "shop_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    image_urls: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated, like Package.sample_image_urls
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Catalogue details (products seeded from shop/products.json carry a slug).
    slug: Mapped[str] = mapped_column(String(80), nullable=True, unique=True)
    category: Mapped[str] = mapped_column(String(30), nullable=True)  # see SHOP_CATEGORIES
    ingredients: Mapped[str] = mapped_column(Text, nullable=True)
    how_to_use: Mapped[str] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str] = mapped_column(Text, nullable=True)
    shelf_life: Mapped[str] = mapped_column(String(120), nullable=True)
    storage: Mapped[str] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Henna, hair and skin products sold under the brand need a manufacturing
    # licence (AYUSH if sold as Ayurvedic, else cosmetic). Such a product can
    # only be published once licence_number is filled in.
    requires_licence: Mapped[bool] = mapped_column(Boolean, default=False)
    licence_number: Mapped[str] = mapped_column(String(80), nullable=True)
    # "photo" (a real product photo) or "illustrative" (AI-made, shown labelled)
    image_kind: Mapped[str] = mapped_column(String(20), default="photo")
    # Which seed image the current one came from ("<file>:<sha>"); null once an admin uploads.
    image_source: Mapped[str] = mapped_column(String(200), nullable=True)

    variants: Mapped[list["ShopProductVariant"]] = relationship(
        order_by="ShopProductVariant.sort_order", cascade="all, delete-orphan", lazy="selectin"
    )


SHOP_CATEGORIES = ("body-art", "hair", "skin", "traditional", "tools", "learn", "decor", "gifts")


class ShopProductVariant(Base):
    """A pack size or shade of a product, with its own MRP and stock. A
    product with active variants is bought by variant."""

    __tablename__ = "shop_product_variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_products.id", ondelete="CASCADE"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)  # net quantity / shade, e.g. "250 g"
    price: Mapped[float] = mapped_column(Float, nullable=False)  # MRP incl. taxes
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# "pending" (created, awaiting payment) -> "paid" -> "shipped" -> "delivered"
# side branch: "cancelled"
SHOP_ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled"]


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    shipping_name: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=False)

    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")

    razorpay_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=True)
    razorpay_signature: Mapped[str] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ShopOrderItem(Base):
    __tablename__ = "shop_order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_orders.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_products.id"), nullable=False)
    # Snapshotted at order time so later price/name edits don't rewrite history.
    product_name: Mapped[str] = mapped_column(String(150), nullable=False)
    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_product_variants.id"), nullable=True)
    variant_label: Mapped[str] = mapped_column(String(60), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)
