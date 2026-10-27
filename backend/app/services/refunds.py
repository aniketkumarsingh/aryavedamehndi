"""Refunds with a tracked lifecycle, for every kind of payment we take.

    issue_refund()            -> Refund "pending", job "refunds.submit" queued
    refunds.submit (job)      -> Razorpay accepts it: "submitted" (or straight
                                 to "processed"); temporary errors retry with
                                 backoff, a rejection marks it "failed"
    refund.processed webhook  -> "processed": amounts, statuses, customer
                                 notice, and a GST credit note if the shop
                                 order had been invoiced
    refund.failed webhook     -> "failed", admins alerted (retry from admin)

A retry can never pay out twice: before submitting, the job asks Razorpay
whether a refund carrying this refund's id already exists, and adopts it.
"""

import logging
import uuid

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.payment_ops import REFUND_TARGETS, Refund
from app.models.shop import ShopOrder
from app.services import razorpay_client
from app.services.doc_numbers import next_document_number
from app.services.jobs import enqueue, job_handler
from app.services.notifications import notify, notify_admins

log = logging.getLogger(__name__)


class RefundError(Exception):
    """A refund that can't be issued (shown to the admin as-is)."""


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


def open_refund_total(db: Session, target_type: str, target_id) -> float:
    """Money already refunded or on its way back for this target."""
    total = (
        db.query(func.coalesce(func.sum(func.coalesce(Refund.amount_refunded, Refund.amount_requested)), 0))
        .filter(Refund.target_type == target_type, Refund.target_id == target_id, Refund.status != "failed")
        .scalar()
    )
    return _money(float(total or 0))


def has_full_refund(db: Session, target_type: str, target_id) -> bool:
    return (
        db.query(Refund)
        .filter(Refund.target_type == target_type, Refund.target_id == target_id, Refund.status != "failed", Refund.amount_requested.is_(None))
        .first()
        is not None
    )


def issue_refund(
    db: Session,
    *,
    target_type: str,
    target_id,
    payment_id: str,
    amount: float | None = None,
    reason: str,
    initiated_by=None,
    refundable: float | None = None,
) -> Refund:
    """Records a refund and queues it for submission. `amount=None` refunds
    everything captured. `refundable` (when known) caps partial refunds at
    what's left after earlier refunds. Doesn't commit."""
    if target_type not in REFUND_TARGETS:
        raise ValueError(f"unknown refund target {target_type!r}")
    if not payment_id:
        raise RefundError("There's no captured payment to refund")
    if has_full_refund(db, target_type, target_id):
        raise RefundError("A full refund for this payment is already under way")
    if amount is not None:
        if amount <= 0:
            raise RefundError("The refund amount must be more than zero")
        if refundable is not None and amount > _money(refundable - open_refund_total(db, target_type, target_id)) + 0.001:
            raise RefundError(f"Only ₹{_money(refundable - open_refund_total(db, target_type, target_id)):g} is left to refund")

    refund = Refund(
        id=uuid.uuid4(),
        target_type=target_type,
        target_id=target_id,
        razorpay_payment_id=payment_id,
        amount_requested=_money(amount) if amount is not None else None,
        reason=reason[:200],
        initiated_by=initiated_by,
        status="pending",
    )
    db.add(refund)
    db.flush()
    enqueue(db, "refunds.submit", {"refund_id": str(refund.id)}, dedupe_key=f"refund-submit:{refund.id}", max_attempts=10)
    if target_type == "shop_order":
        _sync_shop_order(db, db.get(ShopOrder, target_id))
    return refund


def issue_manual_refund(db: Session, *, target_type: str, target_id, amount: float, reference: str, reason: str, initiated_by=None) -> Refund:
    """Records a refund paid by hand (COD orders: UPI transfer to the
    customer), complete on creation; `reference` is the UTR. Doesn't commit."""
    if amount <= 0:
        raise RefundError("The refund amount must be more than zero")
    refund = Refund(id=uuid.uuid4(), target_type=target_type, target_id=target_id, razorpay_payment_id="manual",
                    method="manual_upi", reference=reference[:100], amount_requested=_money(amount), amount_refunded=_money(amount),
                    reason=reason[:200], initiated_by=initiated_by, status="pending")
    db.add(refund)
    db.flush()
    mark_processed(db, refund)
    return refund


def retry_refund(db: Session, refund: Refund) -> None:
    """Admin action on a failed refund: queue it for another submission."""
    if refund.status != "failed":
        raise RefundError("Only a failed refund can be retried")
    refund.status, refund.failure_reason = "pending", None
    enqueue(db, "refunds.submit", {"refund_id": str(refund.id)}, dedupe_key=f"refund-submit:{refund.id}:{utcnow().timestamp():.0f}", max_attempts=10)
    if refund.target_type == "shop_order":
        _sync_shop_order(db, db.get(ShopOrder, refund.target_id))


@job_handler("refunds.submit")
def submit_refund(db: Session, payload: dict) -> str:
    refund = db.get(Refund, uuid.UUID(payload["refund_id"]), with_for_update=True)
    if refund is None or refund.status != "pending":
        return "nothing to do"
    receipt = str(refund.id)

    existing = razorpay_client.find_refund(refund.razorpay_payment_id, receipt)
    if existing is None:
        try:
            existing = razorpay_client.refund_payment(refund.razorpay_payment_id, refund.amount_requested, receipt=receipt)
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                # Razorpay rejected it (already refunded, amount too high...):
                # retrying won't help, a person needs to look.
                description = _razorpay_error(exc)
                mark_failed(db, refund, description)
                return f"rejected: {description}"
            raise  # 429 / 5xx / network - retried with backoff

    refund.razorpay_refund_id = existing.get("id")
    if existing.get("amount") is not None:
        refund.amount_refunded = _money(existing["amount"] / 100)
    if existing.get("status") == "processed":
        mark_processed(db, refund)
        return "processed"
    refund.status = "submitted"
    return "submitted"


def _razorpay_error(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.json()["error"]["description"][:300]
    except Exception:  # noqa: BLE001
        return f"Razorpay returned {exc.response.status_code}"


def _captured_fallback(db: Session, refund: Refund) -> float | None:
    """Refunded amount when the gateway didn't report one (dev stub)."""
    if refund.amount_requested is not None:
        return refund.amount_requested
    if refund.target_type == "shop_order":
        order = db.get(ShopOrder, refund.target_id)
        return _money(order.amount_paid - open_refund_total(db, "shop_order", order.id)) if order else None
    return None


def mark_processed(db: Session, refund: Refund) -> None:
    if refund.status == "processed":
        return
    if refund.amount_refunded is None:
        refund.amount_refunded = _captured_fallback(db, refund)
    refund.status, refund.processed_at, refund.failure_reason = "processed", utcnow(), None
    db.flush()

    amount = f"₹{refund.amount_refunded:g}" if refund.amount_refunded is not None else "Your payment"
    if refund.target_type == "shop_order":
        order = db.get(ShopOrder, refund.target_id)
        if order is not None:
            if order.invoice_number and not refund.credit_note_number:
                refund.credit_note_number = next_document_number(db, "credit_note")
            _sync_shop_order(db, order)
            where = "to your UPI ID" if refund.method == "manual_upi" else "to your original payment method"
            notify(db, order.consumer_id, "shop", "Refund processed",
                   f"{amount} has been refunded {where}. Banks usually show it within 5-7 working days.",
                   f"/shop/orders/{order.id}")
            enqueue(db, "email.shop_refund", {"refund_id": str(refund.id)}, dedupe_key=f"email-refund:{refund.id}")
            from app.services.returns import on_refund_processed

            on_refund_processed(db, refund)
    else:
        _mark_target_refunded(db, refund)
        consumer_id = _consumer_for(db, refund)
        if consumer_id:
            notify(db, consumer_id, "payment", "Refund processed",
                   f"{amount} has been refunded to your original payment method. Banks usually show it within 5-7 working days.", None)


def mark_failed(db: Session, refund: Refund, reason: str) -> None:
    refund.status, refund.failure_reason = "failed", reason[:2000]
    db.flush()
    if refund.target_type == "shop_order":
        _sync_shop_order(db, db.get(ShopOrder, refund.target_id))
    notify_admins(db, "Refund failed", f"{refund.target_type} refund {refund.id}: {reason}"[:300], "/admin")


def _mark_target_refunded(db: Session, refund: Refund) -> None:
    from app.models.booking import Booking
    from app.models.bulk_order import BulkOrder

    model = {"booking_advance": Booking, "bulk_deposit": BulkOrder}.get(refund.target_type)
    row = db.get(model, refund.target_id) if model else None
    if row is not None and row.advance_status == "refund_pending":
        row.advance_status = "refunded"


def _consumer_for(db: Session, refund: Refund):
    from app.models.booking import Booking
    from app.models.bulk_order import BulkOrder
    from app.models.payment import Payment

    if refund.target_type == "booking_advance":
        row = db.get(Booking, refund.target_id)
        return row.consumer_id if row else None
    if refund.target_type == "bulk_deposit":
        row = db.get(BulkOrder, refund.target_id)
        return row.consumer_id if row else None
    if refund.target_type == "booking_payment":
        payment = db.get(Payment, refund.target_id)
        booking = db.get(Booking, payment.booking_id) if payment else None
        return booking.consumer_id if booking else None
    return None


def _paid_basis(order: ShopOrder) -> float:
    """What the customer has paid us for this order."""
    if order.payment_method == "online":
        return order.amount_paid
    # COD: paid at the door, whether or not the courier has remitted yet.
    return order.total_amount if order.payment_status in ("cod_with_courier", "cod_collected", "refund_pending", "partially_refunded", "refunded") else 0


def _sync_shop_order(db: Session, order: ShopOrder | None) -> None:
    """Recomputes a shop order's refunded amount and payment status from its
    refunds - the refunds table is the source of truth."""
    if order is None:
        return
    basis = _paid_basis(order)
    if basis <= 0:
        return
    refunds = db.query(Refund).filter(Refund.target_type == "shop_order", Refund.target_id == order.id).all()
    processed = _money(sum(r.amount_refunded or 0 for r in refunds if r.status == "processed"))
    in_flight = any(r.status in ("pending", "submitted") for r in refunds)
    order.amount_refunded = processed
    if processed >= basis - 0.01:
        order.payment_status = "refunded"
    elif in_flight:
        order.payment_status = "refund_pending"
    elif processed > 0:
        order.payment_status = "partially_refunded"
    elif order.payment_method == "online":
        order.payment_status = "paid"


def find_by_gateway_event(db: Session, entity: dict) -> Refund | None:
    if entity.get("id"):
        if refund := db.query(Refund).filter(Refund.razorpay_refund_id == entity["id"]).first():
            return refund
    ours = (entity.get("notes") or {}).get("refund_id") or entity.get("receipt")
    if ours:
        try:
            return db.get(Refund, uuid.UUID(ours))
        except ValueError:
            return None
    return None
