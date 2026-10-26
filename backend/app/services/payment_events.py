"""Gateway events: stored on arrival, processed by a background job.

The webhook endpoint only verifies the signature, records the event
(duplicates by Razorpay event id are dropped) and queues processing, so it
answers Razorpay in milliseconds and a processing error is retried instead
of being lost. Processing is idempotent, and the browser-side verify
endpoints share the same "mark paid" steps, so whichever arrives first wins.
"""

import hashlib
import json
import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.payment_ops import PaymentEvent
from app.services.jobs import enqueue, job_handler
from app.services.notifications import notify_admins

log = logging.getLogger(__name__)

PAYMENT_EVENTS = {"payment.captured", "order.paid"}
REFUND_EVENTS = {"refund.processed", "refund.failed"}
HANDLED = PAYMENT_EVENTS | REFUND_EVENTS


def record_event(db: Session, body: bytes, event_id: str | None) -> tuple[str, str]:
    """Stores a verified webhook and queues it. Returns (event id, outcome):
    "queued", "ignored" (an event type we don't act on) or "duplicate".
    Razorpay sends X-Razorpay-Event-Id; without one, a hash of the body
    stands in so a redelivery is still recognised. Doesn't commit."""
    event = json.loads(body)
    event_id = event_id or f"sha256:{hashlib.sha256(body).hexdigest()}"
    event_type = event.get("event", "unknown")
    status = "received" if event_type in HANDLED else "ignored"
    row_id = uuid.uuid4()
    inserted = db.execute(
        pg_insert(PaymentEvent)
        .values(id=row_id, provider="razorpay", event_id=event_id, event_type=event_type, payload=event, status=status, received_at=utcnow())
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(PaymentEvent.id)
    ).first()
    if not inserted:
        return event_id, "duplicate"
    if status == "received":
        enqueue(db, "payments.process_event", {"event_row_id": str(row_id)}, dedupe_key=f"event:{event_id}")
        return event_id, "queued"
    return event_id, "ignored"


@job_handler("payments.process_event")
def process_event(db: Session, payload: dict) -> str:
    event = db.get(PaymentEvent, uuid.UUID(payload["event_row_id"]), with_for_update=True)
    if event is None or event.status != "received":
        return "already processed"
    try:
        result = _dispatch(db, event.event_type, event.payload)
    except Exception as exc:
        # Keep the error visible in the admin event log while the job retries.
        db.rollback()
        row = db.get(PaymentEvent, event.id)
        row.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        raise
    event.status, event.result, event.error, event.processed_at = "processed", result[:120], None, utcnow()
    return result


def _dispatch(db: Session, event_type: str, event: dict) -> str:
    payload = event.get("payload", {})
    if event_type in PAYMENT_EVENTS:
        entity = (payload.get("payment") or {}).get("entity") or {}
        if not entity.get("order_id") or entity.get("status") != "captured":
            return "ignored: not a captured order payment"
        return apply_captured_payment(db, entity["order_id"], entity["id"], (entity.get("amount") or 0) / 100)
    if event_type in REFUND_EVENTS:
        from app.services.refunds import find_by_gateway_event, mark_failed, mark_processed

        entity = (payload.get("refund") or {}).get("entity") or {}
        refund = find_by_gateway_event(db, entity)
        if refund is None:
            notify_admins(db, "Unknown refund", f"Razorpay refund {entity.get('id')} ({event_type}) doesn't match any refund here.", "/admin")
            return "unmatched refund"
        refund.razorpay_refund_id = refund.razorpay_refund_id or entity.get("id")
        if entity.get("amount") is not None:
            refund.amount_refunded = round(entity["amount"] / 100, 2)
        if event_type == "refund.processed":
            mark_processed(db, refund)
            return "refund processed"
        mark_failed(db, refund, (entity.get("error_description") or "Razorpay reported the refund as failed"))
        return "refund failed"
    return "ignored"


def apply_captured_payment(db: Session, rp_order_id: str, payment_id: str, amount_rupees: float, alert: bool = True) -> str:
    """Finds what a Razorpay order was for and records the payment against
    it. Returns what it matched. Doesn't commit."""
    # Imported here: these live in routers that themselves use this module.
    from app.models.booking import Booking
    from app.models.bulk_order import BulkOrder
    from app.models.payment import Payment
    from app.models.shop import ShopOrder
    from app.routers.bookings import mark_advance_paid
    from app.routers.bulk_orders import mark_deposit_paid
    from app.routers.payments import _mark_paid
    from app.services.shop_orders import settle_payment

    if order := db.query(ShopOrder).filter(ShopOrder.razorpay_order_id == rp_order_id).with_for_update().first():
        return f"shop_order:{settle_payment(db, order, payment_id, amount=amount_rupees)}"

    if booking := db.query(Booking).filter(Booking.advance_razorpay_order_id == rp_order_id).with_for_update().first():
        return f"booking_advance:{'paid' if mark_advance_paid(db, booking, payment_id) else 'already_paid'}"

    if bulk := db.query(BulkOrder).filter(BulkOrder.advance_razorpay_order_id == rp_order_id).with_for_update().first():
        return f"bulk_deposit:{'paid' if mark_deposit_paid(db, bulk, payment_id) else 'already_paid'}"

    if payment := db.query(Payment).filter(Payment.razorpay_order_id == rp_order_id).with_for_update().first():
        if payment.status == "paid":
            return "booking_payment:already_paid"
        booking = db.get(Booking, payment.booking_id)
        payment.razorpay_payment_id = payment_id
        if booking is not None and booking.status == "design_uploaded":
            _mark_paid(db, booking, payment)
            return "booking_payment:paid"
        if alert:
            notify_admins(db, "Payment needs review", f"₹{amount_rupees:g} was captured for a booking that isn't awaiting payment (Razorpay {payment_id}).", "/admin")
        return "booking_payment:needs_review"

    if alert:
        notify_admins(db, "Unmatched payment", f"₹{amount_rupees:g} captured for unknown Razorpay order {rp_order_id} (payment {payment_id}). Check the Razorpay dashboard.", "/admin")
    return "unmatched"
