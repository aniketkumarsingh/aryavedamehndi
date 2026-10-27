"""Growth: consent records, server-side carts (abandoned-cart reminders),
occasion campaigns and who they reached."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ProductReview(Base):
    """A verified buyer's review: one per product per customer, only after a
    delivered order containing it. Admins can hide a review."""

    __tablename__ = "product_reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "user_id", name="uq_product_review_once"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_product_review_rating"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_products.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_orders.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=True)
    photo_urls: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="published")  # published | hidden
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class LandingPage(Base):
    """A crawlable local page, e.g. /mehndi/bridal-mehndi-artist-south-delhi:
    intro copy from the admin, plus live artists in the city and designs for
    the occasion."""

    __tablename__ = "landing_pages"

    slug: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)  # <title>
    heading: Mapped[str] = mapped_column(String(150), nullable=False)  # <h1>
    intro: Mapped[str] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(60), nullable=True)
    occasion: Mapped[str] = mapped_column(String(30), nullable=True)  # a design occasion key, e.g. "bridal"
    meta_description: Mapped[str] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Referral(Base):
    """A friend who signed up with someone's code. The friend gets money off
    their first shop order; the referrer gets wallet credit once that order
    is delivered and its return window has passed without a return."""

    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")  # pending | credited | void
    first_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_orders.id"), nullable=True)
    reward_amount: Mapped[float] = mapped_column(Float, nullable=True)
    credited_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WalletEntry(Base):
    """The wallet ledger. Credits carry `remaining` and `expires_at` and are
    used oldest-expiry first; a spend records which credits it drew from
    (`allocations`) so a cancelled order can put exactly that back.

    kind: credit (+) | spend (-) | restore (+) | expire (-) | void (-)
    """

    __tablename__ = "wallet_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    remaining: Mapped[float] = mapped_column(Float, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_orders.id"), nullable=True)
    referral_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("referrals.id"), nullable=True)
    allocations: Mapped[list] = mapped_column(JSONB, nullable=True)  # spend: [{"credit_id": "...", "amount": 20.0}]
    reversed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # spend put back (order cancelled)
    note: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ConversionEvent(Base):
    """One server-side conversion sent (or skipped) per event/platform, so a
    retry never double-counts. event_id is shared with the browser pixel for
    de-duplication (the order id for purchases)."""

    __tablename__ = "conversion_events"
    __table_args__ = (UniqueConstraint("event_id", "platform", "event_name", name="uq_conversion_once"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)  # meta | ga4
    event_name: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # sent | skipped | failed
    detail: Mapped[str] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
