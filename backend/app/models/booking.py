import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Booking status progression:
# requested -> negotiating -> confirmed -> artist_enroute -> arrived ->
# in_progress -> design_uploaded -> payment_released -> completed
# side branches: disputed, cancelled
BOOKING_STATUSES = [
    "requested",
    "negotiating",
    "confirmed",
    "artist_enroute",
    "arrived",
    "in_progress",
    "design_uploaded",
    "payment_released",
    "completed",
    "disputed",
    "cancelled",
]


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artist_profiles.user_id"), nullable=False)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(30), default="requested")

    address_text: Mapped[str] = mapped_column(Text, nullable=True)
    location_lat: Mapped[float] = mapped_column(Float, nullable=False)
    location_lng: Mapped[float] = mapped_column(Float, nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    eta_minutes: Mapped[int] = mapped_column(Float, nullable=True)

    # "same" (default, gender-matched) | "any"
    gender_preference: Mapped[str] = mapped_column(String(10), default="same")

    reference_design_image_url: Mapped[str] = mapped_column(String(500), nullable=True)

    agreed_price: Mapped[float] = mapped_column(Float, nullable=True)
    platform_fee: Mapped[float] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=True)

    # How the artist was paid the package amount directly by the consumer -
    # "upi" | "cash" | "bank_transfer" | "other". Separate from `payments`,
    # which only ever covers the platform's own fee.
    settlement_mode: Mapped[str] = mapped_column(String(20), nullable=True)
    settlement_recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Masked calling (Uber-style number privacy) - a per-booking virtual
    # number that bridges calls between consumer and artist without either
    # side seeing the other's real phone number. See
    # app/services/telephony.py - dev-mode returns a fake placeholder
    # number since it needs a real telephony provider account to work.
    masked_call_number: Mapped[str] = mapped_column(String(20), nullable=True)
    masked_call_provider_ref: Mapped[str] = mapped_column(String(100), nullable=True)

    # If the consumer picked one of the artist's declared open slots (see
    # ArtistAvailability) rather than typing a free date/time. Null means
    # either the artist had no slots open, or this booking predates the
    # feature.
    availability_slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artist_availability.id"), nullable=True
    )

    # Booking deposit, snapshotted from Package.advance_amount at booking
    # time (so a later price change doesn't rewrite an in-flight booking).
    # "not_required" | "pending" | "paid" | "refunded" | "forfeited" - see
    # app/routers/bookings.py for the collection/cancellation-refund flow.
    advance_amount: Mapped[float] = mapped_column(Float, default=0)
    advance_status: Mapped[str] = mapped_column(String(20), default="not_required")
    advance_razorpay_order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    advance_razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=True)
    advance_razorpay_signature: Mapped[str] = mapped_column(String(200), nullable=True)
    advance_paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Live location while status == "artist_enroute" - the artist's browser
    # posts periodic updates (see POST /{booking_id}/location) so the
    # consumer can see a live map of how far away their artist is, Uber
    # Eats-style. Stops mattering once they've actually arrived - see
    # artist_arrived_lat/lng below for the one-time arrival snapshot.
    artist_current_lat: Mapped[float] = mapped_column(Float, nullable=True)
    artist_current_lng: Mapped[float] = mapped_column(Float, nullable=True)
    artist_location_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    artist_arrived_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    artist_arrived_lat: Mapped[float] = mapped_column(Float, nullable=True)
    artist_arrived_lng: Mapped[float] = mapped_column(Float, nullable=True)
    artist_completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    artist_completed_lat: Mapped[float] = mapped_column(Float, nullable=True)
    artist_completed_lng: Mapped[float] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NegotiationOffer(Base):
    __tablename__ = "negotiation_offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)
    # "consumer" | "artist"
    proposed_by: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    # "pending" | "accepted" | "rejected" | "countered"
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
