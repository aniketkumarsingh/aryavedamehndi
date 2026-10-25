import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.core.time import utcnow

# Bulk order status progression:
# requested (consumer sent it) -> quoted (our team priced each line inside
# its band and lined up artists) -> confirmed (consumer accepted the quote)
# -> completed. Side branch: cancelled.
BULK_ORDER_STATUSES = ["requested", "quoted", "confirmed", "completed", "cancelled"]


class BulkOrder(Base):
    """One event needing mehndi for several people - a mehndi ceremony,
    sangeet, festival get-together, corporate event... Ops-managed: our team
    quotes it and arranges the artist(s), so there's no single artist_id.

    Priced exactly like booking each person separately (see
    app/services/pricing.py): every line's per-person price stays inside its
    package/design band, the platform fee is per person, and so is the
    deposit."""

    __tablename__ = "bulk_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested")

    # Catalog occasion key (app/schemas/catalog.py DesignOccasion) or one of
    # the bulk-only extras in app/schemas/bulk_order.py.
    occasion: Mapped[str] = mapped_column(String(30), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    address_text: Mapped[str] = mapped_column(Text, nullable=False)
    location_lat: Mapped[float] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float] = mapped_column(Float, nullable=True)
    # "same" (gender-matched artists, the default) | "any"
    gender_preference: Mapped[str] = mapped_column(String(10), default="same")
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    # Set when our team quotes (see POST /admin/bulk-orders/{id}/quote).
    subtotal: Mapped[float] = mapped_column(Float, nullable=True)
    platform_fee: Mapped[float] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=True)
    admin_note: Mapped[str] = mapped_column(Text, nullable=True)
    quoted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # Deposit = sum of each line's per-person package advance, snapshotted at
    # request time like Booking.advance_amount. Same statuses and the same
    # promise: refundable if cancelled before the artists head out (here,
    # before the event day), forfeited after.
    advance_amount: Mapped[float] = mapped_column(Float, default=0)
    advance_status: Mapped[str] = mapped_column(String(20), default="not_required")
    advance_razorpay_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    advance_razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=True)
    advance_razorpay_signature: Mapped[str] = mapped_column(String(200), nullable=True)
    advance_paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    lines: Mapped[list["BulkOrderLine"]] = relationship(
        order_by="BulkOrderLine.sort_order", cascade="all, delete-orphan", back_populates="order"
    )
    consumer: Mapped["User"] = relationship(viewonly=True)

    @property
    def people(self) -> int:
        return sum(line.quantity for line in self.lines)


class BulkOrderLine(Base):
    """One kind of mehndi for a group of people at the event, e.g. "1 x
    bridal full hands" or "25 x simple palm" - optionally a catalog design,
    or the consumer's own uploaded design (priced at the package range)."""

    __tablename__ = "bulk_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bulk_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bulk_orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)
    design_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("designs.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Per-person band and deposit, snapshotted at request time so a later
    # catalog price change doesn't rewrite an in-flight order.
    unit_price_min: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price_max: Mapped[float] = mapped_column(Float, nullable=False)
    unit_advance: Mapped[float] = mapped_column(Float, default=0)
    # Set when quoted - always inside [unit_price_min, unit_price_max].
    unit_price: Mapped[float] = mapped_column(Float, nullable=True)

    order: Mapped[BulkOrder] = relationship(back_populates="lines")
    package: Mapped["Package"] = relationship(viewonly=True)
    design: Mapped["Design"] = relationship(viewonly=True)

    @property
    def package_name(self) -> str | None:
        return self.package.name if self.package else None

    @property
    def category(self) -> str | None:
        return self.package.package_type if self.package else None

    @property
    def design_name(self) -> str | None:
        return self.design.name if self.design else None

    @property
    def design_image_url(self) -> str | None:
        return self.design.image_url if self.design else None
