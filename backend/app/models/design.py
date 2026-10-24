import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow


class DesignUpload(Base):
    __tablename__ = "design_uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), unique=True, nullable=False)
    completed_image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    # "auto_matched" | "needs_consumer_confirmation" | "consumer_confirmed" | "disputed"
    match_status: Mapped[str] = mapped_column(String(30), default="needs_consumer_confirmation")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
