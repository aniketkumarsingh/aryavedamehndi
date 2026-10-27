"""Growth: consent records, server-side carts (abandoned-cart reminders),
occasion campaigns and who they reached."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.database import Base


class ConsentRecord(Base):
    """Every grant or withdrawal of consent, kept as evidence (DPDP Act)."""

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # marketing | analytics | terms
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)  # checkout, booking, profile, unsubscribe_link...
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Cart(Base):
    """A logged-in shopper's cart, kept on the server so we can remind them."""

    __tablename__ = "carts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{product_id, variant_id, quantity}]
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # 0 = no reminder yet, 1 = first reminder sent, 2 = coupon reminder sent (stop)
    reminder_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reminded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    coupon_code: Mapped[str] = mapped_column(String(40), nullable=True)


class Occasion(Base):
    """A dated occasion (Karva Chauth, Teej, Eid, Diwali, wedding season...)
    that triggers a re-booking nudge to past customers shortly before it."""

    __tablename__ = "occasions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    occasion_date: Mapped[date] = mapped_column(Date, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=12)  # send this many days before
    message: Mapped[str] = mapped_column(Text, nullable=True)  # optional extra line
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class CampaignSend(Base):
    __tablename__ = "campaign_sends"
    __table_args__ = (UniqueConstraint("occasion_id", "user_id", name="uq_campaign_send"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occasion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("occasions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    channels: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "app,whatsapp"
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
