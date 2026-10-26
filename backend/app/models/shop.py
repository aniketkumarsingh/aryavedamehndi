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
    # For GST tax invoices; set by the admin (confirm with your accountant).
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=True)
    gst_rate: Mapped[float] = mapped_column(Float, nullable=True)  # percent, included in the MRP

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
# side branch: "cancelled" (from pending or paid; a paid order is refunded)
SHOP_ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled"]
# Moves an admin may make. "paid" is only ever set by payment verification.
SHOP_ORDER_TRANSITIONS = {
    "pending": {"cancelled"},
    "paid": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class ShopCoupon(Base):
    """A discount code for shop orders. Uses are counted from orders that
    carry the code and aren't cancelled, so an abandoned or cancelled order
    gives its use back."""

    __tablename__ = "shop_coupons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)  # stored upper-case
    description: Mapped[str] = mapped_column(String(200), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "percent" | "flat"
    discount_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_discount: Mapped[float] = mapped_column(Float, nullable=True)  # cap for percent coupons
    min_order_amount: Mapped[float] = mapped_column(Float, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=True)  # total uses, null = unlimited
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=True, default=1)  # null = unlimited
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    shipping_name: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(60), nullable=True)  # place of supply for GST
    shipping_pincode: Mapped[str] = mapped_column(String(6), nullable=True)

    total_amount: Mapped[float] = mapped_column(Float, nullable=False)  # what the customer pays
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # total_amount = items_amount - discount_amount + shipping_fee
    items_amount: Mapped[float] = mapped_column(Float, nullable=True)  # null on orders before 0024
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    shipping_fee: Mapped[float] = mapped_column(Float, default=0)
    coupon_code: Mapped[str] = mapped_column(String(40), nullable=True, index=True)

    courier_name: Mapped[str] = mapped_column(String(80), nullable=True)
    tracking_number: Mapped[str] = mapped_column(String(80), nullable=True)
    tracking_url: Mapped[str] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(200), nullable=True)
    refund_status: Mapped[str] = mapped_column(String(20), nullable=True)  # "refunded" | "failed"
    refund_id: Mapped[str] = mapped_column(String(100), nullable=True)
    # Consecutive per financial year (GST rule), given when the order is paid.
    invoice_number: Mapped[str] = mapped_column(String(16), nullable=True, unique=True)

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
    hsn_code: Mapped[str] = mapped_column(String(8), nullable=True)
    gst_rate: Mapped[float] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)


class ShopInvoiceCounter(Base):
    """Last invoice number used in each financial year (April-March)."""

    __tablename__ = "shop_invoice_counters"

    financial_year: Mapped[str] = mapped_column(String(4), primary_key=True)  # "2627"
    last_number: Mapped[int] = mapped_column(Integer, default=0)
