"""Daily reconciliation against Razorpay, plus a refund watchdog.

payments.reconcile (daily, 03:00 IST) lists every payment Razorpay created
in the last 48 hours and:
- records any captured payment we missed (webhook and browser both lost) -
  the same idempotent "mark paid" step, so nothing is applied twice;
- flags captured payments that match nothing here, and shop orders we hold
  as paid that Razorpay doesn't show as captured or refunded.
Each run is stored with its findings; admins are alerted when there are any.

refunds.watchdog (hourly) asks Razorpay about refunds still "submitted"
after a day, in case their webhook never arrived.
"""

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.payment_ops import ReconciliationRun, Refund
from app.models.shop import ShopOrder
from app.services import razorpay_client
from app.services.jobs import job_handler, periodic
from app.services.notifications import notify_admins
from app.services.payment_events import apply_captured_payment

log = logging.getLogger(__name__)
WINDOW = timedelta(hours=48)
SETTLE_GRACE = timedelta(minutes=10)  # leave very recent payments to the webhook


def reconcile(db: Session, now=None) -> ReconciliationRun:
    now = now or utcnow()
    run = ReconciliationRun(window_from=now - WINDOW, window_to=now - SETTLE_GRACE, status="running")
    db.add(run)
    db.flush()
    from app.services.shipping.service import unremitted_cod

    cod_issues = [
        {"type": "cod_not_remitted", "order_id": str(s.order_id), "awb": s.awb, "amount": s.cod_amount,
         "delivered": s.delivered_at.isoformat() if s.delivered_at else None}
        for s in unremitted_cod(db, 10)
    ]
    if not razorpay_client.is_configured():
        run.issues = cod_issues
        run.status = "issues" if cod_issues else "skipped"
        run.note = "Razorpay keys aren't set (dev mode) - only COD remittances checked"
        run.finished_at = utcnow()
        if cod_issues:
            notify_admins(db, "COD not remitted", f"{len(cod_issues)} delivered COD parcel(s) unpaid by the courier after 10 days.", "/admin")
        return run

    epoch = now.__class__(1970, 1, 1)
    payments = razorpay_client.list_payments(int((run.window_from - epoch).total_seconds()), int((run.window_to - epoch).total_seconds()))
    run.payments_seen = len(payments)
    issues, fixed = [], 0
    gateway_status = {}
    for p in payments:
        gateway_status[p["id"]] = p.get("status")
        if p.get("status") != "captured" or not p.get("order_id"):
            continue
        outcome = apply_captured_payment(db, p["order_id"], p["id"], (p.get("amount") or 0) / 100, alert=False)
        if outcome.endswith(":paid") or outcome.endswith(":refunded"):
            fixed += 1
            log.warning("reconciliation recorded a missed payment %s -> %s", p["id"], outcome)
        elif outcome in ("unmatched", "booking_payment:needs_review"):
            issues.append({"type": outcome, "payment_id": p["id"], "order_id": p["order_id"], "amount": (p.get("amount") or 0) / 100})

    held_paid = (
        db.query(ShopOrder)
        .filter(ShopOrder.payment_method == "online", ShopOrder.paid_at >= run.window_from, ShopOrder.paid_at <= run.window_to,
                ShopOrder.razorpay_payment_id.isnot(None))
        .all()
    )
    for order in held_paid:
        if order.razorpay_payment_id.startswith(("pay_dev", "dev_")):
            continue
        status = gateway_status.get(order.razorpay_payment_id)
        if status not in ("captured", "refunded"):
            issues.append({"type": "not_captured_at_gateway", "order_id": str(order.id), "payment_id": order.razorpay_payment_id, "gateway_status": status})

    issues += cod_issues
    run.fixed, run.issues = fixed, issues
    run.status = "issues" if issues else "ok"
    run.finished_at = utcnow()
    if issues or fixed:
        notify_admins(db, "Payment reconciliation", f"{fixed} missed payment(s) recorded, {len(issues)} issue(s) to review.", "/admin")
    return run


@job_handler("payments.reconcile")
def reconcile_job(db: Session, payload: dict) -> str:
    run = reconcile(db)
    return f"{run.status}: {run.payments_seen} seen, {run.fixed} fixed, {len(run.issues)} issues"


@job_handler("refunds.watchdog")
def refund_watchdog(db: Session, payload: dict) -> str:
    from app.services.refunds import mark_failed, mark_processed

    if not razorpay_client.is_configured():
        return "skipped (dev mode)"
    stale = db.query(Refund).filter(Refund.status == "submitted", Refund.updated_at < utcnow() - timedelta(hours=24)).all()
    for refund in stale:
        if not refund.razorpay_refund_id:
            continue
        info = razorpay_client.fetch_refund(refund.razorpay_payment_id, refund.razorpay_refund_id)
        if info.get("amount") is not None:
            refund.amount_refunded = round(info["amount"] / 100, 2)
        if info.get("status") == "processed":
            mark_processed(db, refund)
        elif info.get("status") == "failed":
            mark_failed(db, refund, "Razorpay reports the refund as failed")
    return f"{len(stale)} checked"


periodic("payments.reconcile", timedelta(days=1), offset=timedelta(hours=21, minutes=30))  # 03:00 IST
periodic("refunds.watchdog", timedelta(hours=1))
