"""Bulk / event orders - mehndi for several people at one event.

- Consumers: request (lines of package/design x people), see the estimate,
  accept or cancel the quote, pay the deposit.
- Admins: quote each line at a per-person price inside its band, mark the
  event completed, or cancel it.

Pricing is the booking rules summed per person - see
app/services/pricing.py.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.core.time import utcnow
from app.database import get_db
from app.models.bulk_order import BulkOrder, BulkOrderLine
from app.models.user import User
from app.routers.pricing import estimate_out, priced_line
from app.schemas.booking import AdvancePaymentOrderOut, AdvancePaymentVerifyIn
from app.schemas.bulk_order import (
    AdminBulkOrderOut,
    BulkOrderCancelIn,
    BulkOrderCreateIn,
    BulkOrderOut,
    BulkOrderQuoteIn,
)
from app.services.notifications import notify, notify_admins
from app.services.pricing import quote_totals
from app.services.razorpay_client import create_order, verify_payment_signature
from app.services.refunds import issue_refund

router = APIRouter(prefix="/bulk-orders", tags=["bulk-orders"])
admin_router = APIRouter(prefix="/admin/bulk-orders", tags=["admin"], dependencies=[Depends(require_role("admin"))])
settings = get_settings()

# The bulk version of a booking's "refundable until the artist heads out":
# artists for an event are on their way well before it starts.
REFUND_CUTOFF = timedelta(hours=24)
MIN_LEAD_TIME = timedelta(hours=24)


def _order_out(db: Session, order: BulkOrder) -> BulkOrderOut:
    from app.models.shipping import Shipment, ShipmentEvent
    from app.schemas.shop import ShipmentEventOut, ShipmentOut

    shipments = [
        ShipmentOut(**ShipmentOut.model_validate(s).model_dump(exclude={"events"}),
                    events=[ShipmentEventOut.model_validate(e) for e in db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id == s.id).order_by(ShipmentEvent.occurred_at)])
        for s in db.query(Shipment).filter(Shipment.bulk_order_id == order.id).order_by(Shipment.created_at)
    ]
    return BulkOrderOut(
        **{f: getattr(order, f) for f in BulkOrderOut.model_fields if f not in ("lines", "estimate", "shipments")},
        lines=order.lines,
        estimate=estimate_out(db, order.lines),
        shipments=shipments,
    )


def _admin_order_out(db: Session, order: BulkOrder) -> AdminBulkOrderOut:
    return AdminBulkOrderOut(
        **_order_out(db, order).model_dump(),
        consumer_name=order.consumer.name if order.consumer else None,
        consumer_phone=order.consumer.phone if order.consumer else "",
    )


def _get_order_or_404(db: Session, order_id: uuid.UUID) -> BulkOrder:
    order = db.get(BulkOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _get_own_order(db: Session, order_id: uuid.UUID, user: User) -> BulkOrder:
    order = _get_order_or_404(db, order_id)
    if order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _refund_advance(db: Session, order: BulkOrder) -> str:
    issue_refund(db, target_type="bulk_deposit", target_id=order.id, payment_id=order.advance_razorpay_payment_id,
                 reason="Bulk order cancelled")
    order.advance_status = "refund_pending"  # "refunded" once Razorpay confirms
    return f"Your ₹{order.advance_amount:g} deposit is being refunded - banks usually show it within 5-7 working days."


# ---------------------------------------------------------------- consumer --

@router.post("", response_model=BulkOrderOut)
def create_bulk_order(payload: BulkOrderCreateIn, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    if payload.event_at < utcnow() + MIN_LEAD_TIME:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick an event time at least 24 hours from now so we can line up artists")

    order = BulkOrder(
        consumer_id=user.id,
        occasion=payload.occasion,
        event_at=payload.event_at,
        address_text=payload.address_text,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        gender_preference=payload.gender_preference,
        notes=payload.notes,
    )
    for i, line in enumerate(payload.lines):
        priced = priced_line(db, line.package_id, line.design_id, line.quantity)
        order.lines.append(
            BulkOrderLine(
                package_id=priced.package_id,
                design_id=priced.design_id,
                quantity=line.quantity,
                # A catalog design brings its own image; an uploaded one is
                # only kept when there's no catalog design.
                reference_image_url=None if priced.design_id else line.reference_image_url,
                note=line.note,
                sort_order=i,
                unit_price_min=priced.unit_price_min,
                unit_price_max=priced.unit_price_max,
                unit_advance=priced.unit_advance,
            )
        )
    order.advance_amount = round(sum(l.unit_advance * l.quantity for l in order.lines), 2)
    order.advance_status = "pending" if order.advance_amount > 0 else "not_required"
    db.add(order)
    db.flush()

    notify_admins(
        db,
        "New bulk order request",
        f"{user.name or 'A consumer'} needs mehndi for {order.people} people on {order.event_at:%d %b %Y}.",
        "/admin",
    )
    db.commit()
    db.refresh(order)
    return _order_out(db, order)


@router.get("", response_model=list[BulkOrderOut])
def list_my_bulk_orders(user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    orders = db.query(BulkOrder).filter(BulkOrder.consumer_id == user.id).order_by(BulkOrder.created_at.desc()).all()
    return [_order_out(db, o) for o in orders]


@router.get("/{order_id}", response_model=BulkOrderOut)
def get_bulk_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_id)
    if user.role != "admin" and order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return _order_out(db, order)


@router.post("/{order_id}/accept", response_model=BulkOrderOut)
def accept_quote(order_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    order = _get_own_order(db, order_id, user)
    if order.status != "quoted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "There's no quote to accept on this order")
    order.status = "confirmed"
    order.confirmed_at = utcnow()
    notify_admins(db, "Bulk order confirmed", f"Quote of ₹{order.total_amount:g} accepted for {order.people} people.", "/admin")
    db.commit()
    db.refresh(order)
    return _order_out(db, order)


@router.post("/{order_id}/cancel", response_model=BulkOrderOut)
def cancel_bulk_order(
    order_id: uuid.UUID,
    payload: BulkOrderCancelIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    order = _get_own_order(db, order_id, user)
    if order.status in ("completed", "cancelled"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This order is already {order.status}")

    note = None
    if order.advance_status == "paid":
        if utcnow() >= order.event_at - REFUND_CUTOFF:
            order.advance_status = "forfeited"
            note = f"The ₹{order.advance_amount:g} deposit is forfeited since the event is less than 24 hours away."
        else:
            note = _refund_advance(db, order)

    order.status = "cancelled"
    order.cancel_reason = payload.reason
    notify_admins(db, "Bulk order cancelled by consumer", payload.reason or note, "/admin")
    if note:
        notify(db, user.id, "booking", "Event order cancelled", note, f"/bulk-orders/{order.id}")
    db.commit()
    db.refresh(order)
    return _order_out(db, order)


@router.post("/{order_id}/advance/order", response_model=AdvancePaymentOrderOut)
def create_advance_order(order_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    order = _get_own_order(db, order_id, user)
    if order.status != "confirmed" or order.advance_status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No deposit is due on this order")

    rzp_order = create_order(order.advance_amount, receipt=f"bulk_{order.id.hex}")
    order.advance_razorpay_order_id = rzp_order["id"]
    db.commit()
    return AdvancePaymentOrderOut(
        booking_id=order.id,
        razorpay_order_id=rzp_order["id"],
        razorpay_key_id=settings.razorpay_key_id or "dev_mode_no_key",
        amount=order.advance_amount,
        currency="INR",
    )


def mark_deposit_paid(db: Session, order: BulkOrder, payment_id: str, signature: str | None = None) -> bool:
    """Records the deposit as paid - from the customer's browser or the
    Razorpay webhook, whichever arrives first. Returns False if it was
    already recorded. Doesn't commit."""
    if order.advance_status == "paid":
        return False
    order.advance_razorpay_payment_id = payment_id
    order.advance_razorpay_signature = signature
    order.advance_status = "paid"
    order.advance_paid_at = utcnow()
    notify_admins(db, "Bulk order deposit paid", f"₹{order.advance_amount:g} received - the event is secured.", "/admin")
    return True


@router.post("/{order_id}/advance/verify", response_model=BulkOrderOut)
def verify_advance_payment(
    order_id: uuid.UUID,
    payload: AdvancePaymentVerifyIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    order = _get_own_order(db, order_id, user)
    db.refresh(order, with_for_update=True)  # one settle at a time (see the webhook)
    if order.advance_razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching deposit payment order")
    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    mark_deposit_paid(db, order, payload.razorpay_payment_id, payload.razorpay_signature)
    db.commit()
    db.refresh(order)
    return _order_out(db, order)


# ------------------------------------------------------------------- admin --

@admin_router.get("", response_model=list[AdminBulkOrderOut])
def admin_list_bulk_orders(
    status_filter: str = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(BulkOrder).order_by(BulkOrder.event_at)
    if status_filter != "all":
        query = query.filter(BulkOrder.status == status_filter)
    return [_admin_order_out(db, o) for o in query.offset(offset).limit(limit).all()]


@admin_router.post("/{order_id}/quote", response_model=AdminBulkOrderOut)
def quote_bulk_order(order_id: uuid.UUID, payload: BulkOrderQuoteIn, db: Session = Depends(get_db)):
    """Prices every line at a per-person amount inside the band the consumer
    was shown - re-quoting is allowed until they accept."""
    order = _get_order_or_404(db, order_id)
    if order.status not in ("requested", "quoted"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a requested or quoted order can be (re)quoted")

    prices = {q.line_id: q.unit_price for q in payload.lines}
    if set(prices) != {l.id for l in order.lines}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quote every line of the order, and only its lines")
    for line in order.lines:
        price = prices[line.id]
        if not line.unit_price_min <= price <= line.unit_price_max:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{line.design_name or line.package_name}: price must be between ₹{line.unit_price_min:g} and "
                f"₹{line.unit_price_max:g} per person - the same range as booking on its own",
            )
        line.unit_price = price

    totals = quote_totals(db, [(l.unit_price, l.quantity) for l in order.lines])
    order.subtotal = totals["subtotal"]
    order.platform_fee = totals["platform_fee"]
    order.total_amount = totals["total_amount"]
    order.admin_note = payload.admin_note
    order.status = "quoted"
    order.quoted_at = utcnow()
    notify(
        db,
        order.consumer_id,
        "booking",
        "Your event quote is ready",
        f"₹{order.total_amount:g} for {order.people} people - review and accept it to lock in your artists.",
        f"/bulk-orders/{order.id}",
    )
    db.commit()
    db.refresh(order)
    return _admin_order_out(db, order)


@admin_router.post("/{order_id}/complete", response_model=AdminBulkOrderOut)
def complete_bulk_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_id)
    if order.status != "confirmed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a confirmed order can be completed")
    if order.advance_status == "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The deposit hasn't been paid yet")
    order.status = "completed"
    notify(db, order.consumer_id, "booking", "Event order completed", "Thank you for celebrating with AryaVeda Mehndi!", f"/bulk-orders/{order.id}")
    db.commit()
    db.refresh(order)
    return _admin_order_out(db, order)


@admin_router.post("/{order_id}/cancel", response_model=AdminBulkOrderOut)
def admin_cancel_bulk_order(order_id: uuid.UUID, payload: BulkOrderCancelIn, db: Session = Depends(get_db)):
    """Our side cancelling (e.g. no artists free) - any paid deposit is
    always refunded in full."""
    order = _get_order_or_404(db, order_id)
    if order.status in ("completed", "cancelled"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This order is already {order.status}")
    note = _refund_advance(db, order) if order.advance_status == "paid" else None
    order.status = "cancelled"
    order.cancel_reason = payload.reason
    body = " ".join(filter(None, [payload.reason, note]))
    notify(db, order.consumer_id, "booking", "Event order cancelled", body or None, f"/bulk-orders/{order.id}")
    db.commit()
    db.refresh(order)
    return _admin_order_out(db, order)

