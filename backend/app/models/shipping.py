"""Shipments and tracking. An order can have more than one shipment (a
split or a re-ship), so tracking lives here; the courier/tracking columns
on ShopOrder are kept in step for older orders and simple reads."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.database import Base

# Our tracking vocabulary; each provider maps its own statuses onto these.
#   booked -> picked_up -> in_transit -> out_for_delivery -> delivered
#   ndr: a delivery attempt failed;  rto: returning to us;  rto_delivered: back with us
SHIPMENT_STATUSES = ("booked", "picked_up", "in_transit", "out_for_delivery", "delivered", "ndr", "rto", "rto_delivered", "cancelled")
TERMINAL_SHIPMENT_STATUSES = ("delivered", "rto_delivered", "cancelled")


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("provider", "awb", name="uq_shipments_provider_awb"),
        Index("ix_shipments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shop_orders.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # "manual", later e.g. "shiprocket"
    awb: Mapped[str] = mapped_column(String(80), nullable=True)  # courier airway bill / tracking number
    courier_name: Mapped[str] = mapped_column(String(80), nullable=True)
    tracking_url: Mapped[str] = mapped_column(String(300), nullable=True)
    label_url: Mapped[str] = mapped_column(String(500), nullable=True)  # the courier's label; ours is generated on request
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")
    weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    length_cm: Mapped[float] = mapped_column(Float, nullable=False)
    breadth_cm: Mapped[float] = mapped_column(Float, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    cod_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)  # to collect at the door
    shipping_charge: Mapped[float] = mapped_column(Float, nullable=True)  # what the courier bills us, when known
    pickup_scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=True)  # the provider's booking response
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ShipmentEvent(Base):
    """One tracking scan. (shipment, external_id) is unique, so the same
    scan arriving by webhook and by poll is stored once."""

    __tablename__ = "shipment_events"
    __table_args__ = (UniqueConstraint("shipment_id", "external_id", name="uq_shipment_events_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=True)
    location: Mapped[str] = mapped_column(String(120), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # manual | webhook | poll | system
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PincodeServiceability(Base):
    """Provider answers per PIN code, cached for a day."""

    __tablename__ = "pincode_serviceability"

    pincode: Mapped[str] = mapped_column(String(6), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    deliverable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cod_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eta_min_days: Mapped[int] = mapped_column(Integer, nullable=True)
    eta_max_days: Mapped[int] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShippingWebhookEvent(Base):
    """Courier webhooks, stored before processing (same inbox pattern as
    payment events)."""

    __tablename__ = "shipping_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="received")  # received | processed | failed
    result: Mapped[str] = mapped_column(String(160), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    processed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
