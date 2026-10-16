import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # "regular" | "bridal" | "party" | "festival" | "feet"
    package_type: Mapped[str] = mapped_column(String(30), nullable=False, default="regular")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    price_min: Mapped[float] = mapped_column(Float, nullable=False)
    price_max: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    negotiable: Mapped[bool] = mapped_column(Boolean, default=True)
    sample_image_urls: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated
    # Non-refundable-after-dispatch booking deposit, collected through the
    # app once the consumer and artist agree a price - protects the artist
    # against a no-show after they've already traveled. 0 = no advance
    # required for this package. See Booking.advance_* for the per-booking
    # snapshot and app/routers/bookings.py for the collection/forfeit flow.
    advance_amount: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
