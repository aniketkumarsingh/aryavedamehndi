"""Payment operations records: the inbox of gateway events, refunds with
their lifecycle, reconciliation runs, and idempotency keys for
order-creating requests."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.database import Base


class PaymentEvent(Base):
    """Every webhook Razorpay sends, stored before it's processed (inbox
    pattern). The gateway's event id is unique, so a redelivered event is
    recorded and processed once."""

    __tablename__ = "payment_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="razorpay")
    event_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # received -> processed | ignored | failed
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="received")
    result: Mapped[str] = mapped_column(String(120), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


# What a refund is for. Each maps to the record whose money is returned.
REFUND_TARGETS = ("shop_order", "booking_advance", "bulk_deposit", "booking_payment")
# pending (queued) -> submitted (Razorpay accepted it) -> processed
#                                                      -> failed
REFUND_STATUSES = ("pending", "submitted", "processed", "failed")


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    razorpay_payment_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    razorpay_refund_id: Mapped[str] = mapped_column(String(100), nullable=True, unique=True)
    # Requested amount; null means "everything captured" (correct even when a
    # Razorpay Offer made the captured amount smaller than the order total).
    amount_requested: Mapped[float] = mapped_column(Float, nullable=True)
    amount_refunded: Mapped[float] = mapped_column(Float, nullable=True)  # as reported by Razorpay
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    reason: Mapped[str] = mapped_column(String(200), nullable=True)
    initiated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=True)
    # GST credit note, issued when the refunded shop order had been invoiced.
    credit_note_number: Mapped[str] = mapped_column(String(16), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ReconciliationRun(Base):
    """One pass comparing Razorpay's captured payments with our records."""

    __tablename__ = "reconciliation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    window_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="running")  # running | ok | issues | skipped | failed
    payments_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fixed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class IdempotencyKey(Base):
    """Remembers the response to a request sent with an Idempotency-Key
    header, so a double-tap or network retry returns the same order instead
    of placing a second one."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "shop.create_order"
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=True)  # null while the first request is in flight
    response: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
