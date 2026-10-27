"""Shop order rules shared by the customer, admin, webhook and worker paths.

Two separate state machines live on an order:

    status          pending -> confirmed -> shipped -> delivered
                          \\-> cancelled  <-/ (before dispatch)
    payment_status  online: unpaid -> paid -> refund_pending ->
                            partially_refunded / refunded;  void if
                            cancelled before any money moved
                    COD:    cod_due -> cod_collected (on delivery)

Covered here: pricing (coupon, delivery charge, COD fee), coupon and COD
eligibility, confirming a payment (from the browser, the webhook or
reconciliation - idempotent), cancelling (stock back, refund queued),
dispatch (GST invoice issued) and delivery (COD collected), and the
scheduled release of unpaid orders.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.shop import ShopCoupon, ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.services.doc_numbers import next_document_number
from app.services.jobs import enqueue, job_handler, periodic
from app.services.notifications import notify, notify_admins
from app.services.platform_settings import get_platform_settings
from app.services.refunds import RefundError, issue_refund

# Orders holding stock / counting against limits.
OPEN_STATUSES = ("pending", "confirmed", "shipped")


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def normalise_code(code: str) -> str:
    return code.strip().upper()


# ----------------------------------------------------------------- pricing --

def coupon_discount(coupon: ShopCoupon, items_amount: float) -> float:
    if coupon.discount_type == "percent":
        discount = items_amount * coupon.discount_value / 100
        if coupon.max_discount:
            discount = min(discount, coupon.max_discount)
    else:
        discount = coupon.discount_value
    return money(min(discount, items_amount))


def coupon_problem(db: Session, coupon: ShopCoupon | None, user_id, items_amount: float) -> str | None:
    """Why this coupon can't be used on this order, or None if it can."""
    if coupon is None or not coupon.is_active:
        return "This coupon code isn't valid"
    now = utcnow()
    if coupon.starts_at and now < coupon.starts_at:
        return "This coupon isn't active yet"
    if coupon.expires_at and now > coupon.expires_at:
        return "This coupon has expired"
    if items_amount < (coupon.min_order_amount or 0):
        return f"Add items worth ₹{money(coupon.min_order_amount - items_amount):g} more to use this coupon"
    uses = db.query(ShopOrder).filter(ShopOrder.coupon_code == coupon.code, ShopOrder.status != "cancelled")
    if coupon.usage_limit is not None and uses.count() >= coupon.usage_limit:
        return "This coupon has been fully used"
    if coupon.per_user_limit is not None and uses.filter(ShopOrder.consumer_id == user_id).count() >= coupon.per_user_limit:
        return "You've already used this coupon"
    return None


def price_order(db: Session, items_amount: float, coupon: ShopCoupon | None, payment_method: str = "online") -> dict:
    """Discount, delivery, COD fee and total for an items total (coupon
    already checked)."""
    s = get_platform_settings(db)
    discount = coupon_discount(coupon, items_amount) if coupon else 0.0
    after_discount = money(items_amount - discount)
    free_above = float(s["shop_free_shipping_above"])
    shipping = 0.0 if after_discount >= free_above else money(float(s["shop_shipping_fee"]))
    cod_fee = money(float(s["shop_cod_fee"])) if payment_method == "cod" else 0.0
    return {
        "items_amount": money(items_amount),
        "discount_amount": discount,
        "shipping_fee": shipping,
        "cod_fee": cod_fee,
        "total_amount": money(after_discount + shipping + cod_fee),
        "free_shipping_above": free_above,
    }


def cod_problem(db: Session, user_id, total_without_cod_fee: float) -> str | None:
    """Why Cash on Delivery isn't available for this order, or None."""
    s = get_platform_settings(db)
    if not s["shop_cod_enabled"]:
        return "Cash on Delivery isn't available right now"
    if total_without_cod_fee > float(s["shop_cod_max_order"]):
        return f"Cash on Delivery is available on orders up to ₹{float(s['shop_cod_max_order']):g} - please pay online"
    open_cod = (
        db.query(ShopOrder)
        .filter(ShopOrder.consumer_id == user_id, ShopOrder.payment_method == "cod", ShopOrder.status.in_(OPEN_STATUSES))
        .count()
    )
    if open_cod >= int(s["shop_cod_max_open_orders"]):
        return "You already have Cash on Delivery orders on the way - please pay online for this one"
    return None


# ------------------------------------------------------------ transitions --

def _restock(db: Session, order: ShopOrder) -> None:
    for item in db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id):
        row = db.get(ShopProductVariant, item.variant_id) if item.variant_id else db.get(ShopProduct, item.product_id)
        if row is not None:
            row.stock_quantity += item.quantity


def confirm_cod(db: Session, order: ShopOrder) -> None:
    """A Cash on Delivery order is confirmed as soon as it's placed."""
    order.status, order.payment_status, order.confirmed_at = "confirmed", "cod_due", utcnow()
    notify(db, order.consumer_id, "shop", "Order confirmed",
           f"Your Cash on Delivery order is confirmed. Please keep ₹{order.total_amount:g} ready at delivery.", f"/shop/orders/{order.id}")
    enqueue(db, "email.shop_order_confirmed", {"order_id": str(order.id)}, dedupe_key=f"email-confirmed:{order.id}")


def cancel_order(db: Session, order: ShopOrder, reason: str, initiated_by=None) -> None:
    """Cancels an order before dispatch: stock goes back, and money paid
    online is refunded in full (queued; see app/services/refunds.py).
    Doesn't commit."""
    order.status = "cancelled"
    order.cancelled_at = utcnow()
    order.cancel_reason = reason[:200]
    _restock(db, order)
    if order.payment_status == "paid" and order.razorpay_payment_id:
        issue_refund(db, target_type="shop_order", target_id=order.id, payment_id=order.razorpay_payment_id,
                     reason=f"Order cancelled: {reason}", initiated_by=initiated_by)
    elif order.payment_status in ("unpaid", "cod_due"):
        order.payment_status = "void"


def mark_shipped(db: Session, order: ShopOrder, courier: str | None, tracking_number: str | None, tracking_url: str | None) -> None:
    """Dispatch is the time of supply for goods, so the GST invoice is
    issued here and emailed with the dispatch notice."""
    now = utcnow()
    order.status = "shipped"
    order.shipped_at = order.shipped_at or now
    order.courier_name = courier or order.courier_name
    order.tracking_number = tracking_number or order.tracking_number
    order.tracking_url = tracking_url or order.tracking_url
    if not order.invoice_number:
        order.invoice_number, order.invoiced_at = next_document_number(db, "invoice"), now
    message = "Your order has shipped."
    if order.tracking_number:
        message = f"Your order has shipped with {order.courier_name or 'our courier'} - tracking no. {order.tracking_number}."
    notify(db, order.consumer_id, "shop", "Order shipped", message, f"/shop/orders/{order.id}")
    enqueue(db, "email.shop_order_shipped", {"order_id": str(order.id)}, dedupe_key=f"email-shipped:{order.id}")


def mark_returned(db: Session, order: ShopOrder, reason: str, initiated_by=None, condition: str = "good") -> None:
    """A shipped parcel came back (refused at the door, undeliverable - RTO)
    and an admin has checked it. Stock goes back only if it's in good
    condition; nothing is owed on Cash on Delivery; money paid online is
    refunded in full (with a credit note, as the order was invoiced)."""
    order.status = "returned"
    order.cancel_reason = reason[:200]
    order.return_condition = condition
    if condition == "good":
        _restock(db, order)
    if order.payment_method == "cod" and order.payment_status == "cod_due":
        order.payment_status = "void"
    elif order.payment_status in ("paid", "partially_refunded") and order.razorpay_payment_id:
        remaining = money(order.amount_paid - order.amount_refunded)
        if remaining > 0:
            issue_refund(db, target_type="shop_order", target_id=order.id, payment_id=order.razorpay_payment_id,
                         amount=None if order.payment_status == "paid" else remaining,
                         reason=f"Parcel returned: {reason}", initiated_by=initiated_by, refundable=order.amount_paid)
    notify(db, order.consumer_id, "shop", "Order returned",
           "Your parcel came back to us." + (" Your payment is being refunded." if order.payment_method == "online" else ""),
           f"/shop/orders/{order.id}")


def mark_delivered(db: Session, order: ShopOrder) -> None:
    order.status, order.delivered_at = "delivered", utcnow()
    if order.payment_method == "cod" and order.payment_status == "cod_due":
        # The customer has paid the courier; it's ours once remitted.
        order.payment_status = "cod_with_courier"
    notify(db, order.consumer_id, "shop", "Order delivered", "Your order has been delivered. We hope you love it!", f"/shop/orders/{order.id}")
    enqueue(db, "email.shop_delivered", {"order_id": str(order.id)}, dedupe_key=f"email-delivered:{order.id}")


def refundable_amount(order: ShopOrder) -> float:
    return money(order.amount_paid if order.payment_method == "online" else 0)


def refund_order(db: Session, order: ShopOrder, amount: float | None, reason: str, initiated_by) -> None:
    """Admin refund on a dispatched prepaid order (e.g. a damaged item):
    full when `amount` is None, else partial. Doesn't change the fulfilment
    status. Before dispatch, cancel instead - a refund then would leave the
    GST invoice issued at dispatch overstating the sale."""
    if order.payment_method != "online" or order.payment_status not in ("paid", "partially_refunded", "refund_pending"):
        raise RefundError("Only orders paid online can be refunded here")
    if order.status not in ("shipped", "delivered"):
        raise RefundError("This order hasn't shipped yet - cancel it instead (that refunds the payment in full)")
    issue_refund(db, target_type="shop_order", target_id=order.id, payment_id=order.razorpay_payment_id, amount=amount,
                 reason=reason, initiated_by=initiated_by, refundable=refundable_amount(order))


# ---------------------------------------------------------------- payment --

def is_stale(db: Session, order: ShopOrder) -> bool:
    window = int(get_platform_settings(db)["shop_payment_window_minutes"])
    return order.status == "pending" and order.created_at < utcnow() - timedelta(minutes=window)


def settle_payment(db: Session, order: ShopOrder, payment_id: str, signature: str | None = None, amount: float | None = None) -> str:
    """Records a captured payment against an order - from the browser, the
    webhook or reconciliation, whichever comes first. Returns "paid",
    "already_paid", or "refunded" when the order had expired or been
    cancelled before the money arrived (it's then refunded once).
    `amount` is what Razorpay captured, when known (it can be below the
    total if a Razorpay Offer applied). Doesn't commit."""
    if order.razorpay_payment_id == payment_id and order.payment_status != "unpaid":
        # Seen before. The browser can't report the captured amount; the
        # webhook can - keep the gateway's figure (a Razorpay Offer may have
        # made it smaller than the total) while nothing has been refunded.
        if amount and order.payment_status == "paid" and abs(order.amount_paid - amount) > 0.009:
            order.amount_paid = money(amount)
        return "already_paid" if order.status != "cancelled" else "refunded"
    if order.razorpay_payment_id and order.razorpay_payment_id != payment_id:
        # A second, different payment for an order that already has one (a
        # double charge). Never overwrite the first; a person decides.
        notify_admins(db, "Duplicate payment", f"Order {str(order.id)[:8]} already has payment {order.razorpay_payment_id}; "
                      f"another payment {payment_id} arrived. Refund the extra one from the Razorpay dashboard.", "/admin")
        return "duplicate_needs_review"
    if order.status == "pending" and is_stale(db, order):
        cancel_order(db, order, "Payment not completed in time")
    if order.status != "pending":
        # Money for an order that's no longer waiting (its stock may be gone).
        order.razorpay_payment_id = payment_id
        order.amount_paid = money(amount if amount else order.total_amount)
        order.payment_status = "paid"
        issue_refund(db, target_type="shop_order", target_id=order.id, payment_id=payment_id,
                     reason="Payment arrived after the order had expired")
        notify(db, order.consumer_id, "shop", "Payment refunded",
               "Your payment arrived after the order had expired, so it's being refunded in full. Please order again.",
               f"/shop/orders/{order.id}")
        return "refunded"
    now = utcnow()
    order.razorpay_payment_id = payment_id
    order.razorpay_signature = signature
    order.status, order.payment_status = "confirmed", "paid"
    order.amount_paid = money(amount if amount else order.total_amount)
    order.paid_at = order.confirmed_at = now
    notify(db, order.consumer_id, "shop", "Order confirmed", f"Your ₹{order.amount_paid:g} payment is received and your order will ship soon.", f"/shop/orders/{order.id}")
    enqueue(db, "email.shop_order_confirmed", {"order_id": str(order.id)}, dedupe_key=f"email-confirmed:{order.id}")
    return "paid"


def release_stale_orders(db: Session) -> int:
    """Cancels unpaid online orders older than the payment window, giving
    back their stock and coupon uses. Doesn't commit."""
    window = int(get_platform_settings(db)["shop_payment_window_minutes"])
    cutoff = utcnow() - timedelta(minutes=window)
    stale = (
        db.query(ShopOrder)
        .filter(ShopOrder.status == "pending", ShopOrder.created_at < cutoff)
        .with_for_update(skip_locked=True)
        .all()
    )
    for order in stale:
        cancel_order(db, order, "Payment not completed in time")
    return len(stale)


@job_handler("shop.release_unpaid")
def release_unpaid_job(db: Session, payload: dict) -> str:
    return f"{release_stale_orders(db)} released"


periodic("shop.release_unpaid", timedelta(minutes=5))
