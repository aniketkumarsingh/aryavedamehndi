import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), unique=True, nullable=False)
    razorpay_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=True)
    razorpay_signature: Mapped[str] = mapped_column(String(200), nullable=True)

    # `is_full_escrow` = the consumer paid the whole booking (package +
    # platform fee) through the app, because the artist has a Razorpay
    # Route linked account - `amount` is then the full total and
    # `artist_share`/`platform_share` record the Route split.
    # When False (no linked account yet), `amount` is just the platform
    # fee as before, and the package amount is settled directly between
    # consumer and artist (tracked via Booking.settlement_mode).
    is_full_escrow: Mapped[bool] = mapped_column(Boolean, default=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    artist_share: Mapped[float] = mapped_column(Float, nullable=True)
    platform_share: Mapped[float] = mapped_column(Float, nullable=True)
    # "not_applicable" | "pending" | "transferred" | "failed"
    payout_status: Mapped[str] = mapped_column(String(20), default="not_applicable")
    razorpay_transfer_id: Mapped[str] = mapped_column(String(100), nullable=True)

    currency: Mapped[str] = mapped_column(String(10), default="INR")
    # "created" | "paid" | "failed"
    status: Mapped[str] = mapped_column(String(20), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
