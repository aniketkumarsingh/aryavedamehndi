"""Razorpay webhook: Razorpay calls this directly when a payment is
captured, so a payment is recorded even if the customer's browser never
reports back (closed tab, lost signal, switching back from a UPI app).
It applies the same "mark paid" step as the browser-side verify endpoints,
whichever arrives first wins and the other is a no-op.

Set up in Razorpay Dashboard -> Settings -> Webhooks:
  URL     <PUBLIC_API_URL>/payments/razorpay/webhook
  Events  payment.captured, order.paid
  Secret  the same value as RAZORPAY_WEBHOOK_SECRET
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.booking import Booking
from app.models.bulk_order import BulkOrder
from app.models.payment import Payment
from app.models.shop import ShopOrder
from app.routers.bookings import mark_advance_paid
from app.routers.bulk_orders import mark_deposit_paid
from app.routers.payments import _mark_paid
from app.services.notifications import notify_admins
from app.services.razorpay_client import verify_webhook_signature
from app.services.shop_orders import settle_payment

router = APIRouter(prefix="/payments", tags=["payments"])
log = logging.getLogger(__name__)

HANDLED_EVENTS = {"payment.captured", "order.paid"}


def apply_captured_payment(db: Session, rp_order_id: str, payment_id: str, amount_rupees: float) -> str:
    """Finds what a Razorpay order was for and records the payment against
    it. Returns what it matched (for the response and logs). Doesn't commit."""
    if order := db.query(ShopOrder).filter(ShopOrder.razorpay_order_id == rp_order_id).first():
        return f"shop_order:{settle_payment(db, order, payment_id)}"

    if booking := db.query(Booking).filter(Booking.advance_razorpay_order_id == rp_order_id).first():
        return f"booking_advance:{'paid' if mark_advance_paid(db, booking, payment_id) else 'already_paid'}"

    if bulk := db.query(BulkOrder).filter(BulkOrder.advance_razorpay_order_id == rp_order_id).first():
        return f"bulk_deposit:{'paid' if mark_deposit_paid(db, bulk, payment_id) else 'already_paid'}"

    if payment := db.query(Payment).filter(Payment.razorpay_order_id == rp_order_id).first():
        if payment.status == "paid":
            return "booking_payment:already_paid"
        booking = db.get(Booking, payment.booking_id)
        payment.razorpay_payment_id = payment_id
        if booking is not None and booking.status == "design_uploaded":
            _mark_paid(db, booking, payment)
            return "booking_payment:paid"
        notify_admins(db, "Payment needs review", f"₹{amount_rupees:g} was captured for a booking that isn't awaiting payment (Razorpay {payment_id}).", "/admin")
        return "booking_payment:needs_review"

    # Money arrived for an order we don't know - never lose track of it.
    notify_admins(db, "Unmatched payment", f"₹{amount_rupees:g} captured for unknown Razorpay order {rp_order_id} (payment {payment_id}). Check the Razorpay dashboard.", "/admin")
    return "unmatched"


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_webhook_signature(body, request.headers.get("X-Razorpay-Signature")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")

    event = json.loads(body)
    if event.get("event") not in HANDLED_EVENTS:
        return {"status": "ignored"}
    entity = (event.get("payload", {}).get("payment") or {}).get("entity") or {}
    rp_order_id, payment_id = entity.get("order_id"), entity.get("id")
    if not rp_order_id or not payment_id or entity.get("status") != "captured":
        return {"status": "ignored"}

    outcome = apply_captured_payment(db, rp_order_id, payment_id, (entity.get("amount") or 0) / 100)
    db.commit()
    log.info("razorpay webhook %s %s -> %s", event.get("event"), payment_id, outcome)
    # Always 200 once the signature checks out, so Razorpay doesn't retry
    # events we've deliberately handled (including unmatched ones).
    return {"status": "ok", "result": outcome}
