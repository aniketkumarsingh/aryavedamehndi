"""Shop order rules shared by the customer and admin endpoints: pricing
(coupon discount + delivery charge), coupon eligibility, cancelling (stock
back, refund if paid) and releasing unpaid orders whose payment window has
passed. There's no background worker, so stale orders are released lazily
whenever orders are created, paid for or listed by an admin."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.shop import ShopCoupon, ShopInvoiceCounter, ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.services.notifications import notify
from app.services.platform_settings import get_platform_settings
from app.services.razorpay_client import refund_payment


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def normalise_code(code: str) -> str:
    return code.strip().upper()


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


def price_order(db: Session, items_amount: float, coupon: ShopCoupon | None) -> dict:
    """discount, delivery and total for an items total (coupon already checked)."""
    s = get_platform_settings(db)
    discount = coupon_discount(coupon, items_amount) if coupon else 0.0
    after_discount = money(items_amount - discount)
    free_above = float(s["shop_free_shipping_above"])
    shipping = 0.0 if after_discount >= free_above else money(float(s["shop_shipping_fee"]))
    return {
        "items_amount": money(items_amount),
        "discount_amount": discount,
        "shipping_fee": shipping,
        "total_amount": money(after_discount + shipping),
        "free_shipping_above": free_above,
    }


def _restock(db: Session, order: ShopOrder) -> None:
    for item in db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id):
        row = db.get(ShopProductVariant, item.variant_id) if item.variant_id else db.get(ShopProduct, item.product_id)
        if row is not None:
            row.stock_quantity += item.quantity


def cancel_order(db: Session, order: ShopOrder, reason: str) -> None:
    """Cancels a pending or paid order: stock goes back, and a paid order is
    refunded in full. A failed refund is recorded for the admin to retry by
    hand rather than blocking the cancellation. Doesn't commit."""
    was_paid = order.status == "paid"
    order.status = "cancelled"
    order.cancelled_at = utcnow()
    order.cancel_reason = reason[:200]
    _restock(db, order)
    if was_paid and order.razorpay_payment_id:
        try:
            refund = refund_payment(order.razorpay_payment_id)
            order.refund_status, order.refund_id = "refunded", refund.get("id")
        except Exception:  # noqa: BLE001 - recorded, admin retries in the Razorpay dashboard
            order.refund_status = "failed"


def is_stale(db: Session, order: ShopOrder) -> bool:
    window = int(get_platform_settings(db)["shop_payment_window_minutes"])
    return order.status == "pending" and order.created_at < utcnow() - timedelta(minutes=window)


def release_stale_orders(db: Session) -> int:
    """Cancels unpaid orders older than the payment window, returning their
    stock and coupon uses. Doesn't commit."""
    window = int(get_platform_settings(db)["shop_payment_window_minutes"])
    cutoff = utcnow() - timedelta(minutes=window)
    stale = db.query(ShopOrder).filter(ShopOrder.status == "pending", ShopOrder.created_at < cutoff).all()
    for order in stale:
        cancel_order(db, order, "Payment not completed in time")
    return len(stale)


def settle_payment(db: Session, order: ShopOrder, payment_id: str, signature: str | None = None) -> str:
    """Records a captured payment against an order - from the customer's
    browser or from the Razorpay webhook, whichever arrives first. Returns
    "paid", "already_paid", or "refunded" when the order had expired or been
    cancelled before the money arrived (its stock may be gone), in which
    case the payment is refunded once. Doesn't commit."""
    if order.status == "paid":
        return "already_paid"
    if order.status == "pending" and is_stale(db, order):
        cancel_order(db, order, "Payment not completed in time")
    if order.status != "pending":
        if not (order.razorpay_payment_id == payment_id and order.refund_status == "refunded"):
            refund = refund_payment(payment_id)
            order.razorpay_payment_id = payment_id
            order.refund_status, order.refund_id = "refunded", refund.get("id")
            notify(db, order.consumer_id, "shop", "Payment refunded",
                   "Your payment arrived after the order had expired, so it has been refunded in full. Please order again.",
                   f"/shop/orders/{order.id}")
        return "refunded"
    order.razorpay_payment_id = payment_id
    order.razorpay_signature = signature
    order.status = "paid"
    order.paid_at = utcnow()
    order.invoice_number = order.invoice_number or next_invoice_number(db)
    notify(db, order.consumer_id, "shop", "Order confirmed", f"Your ₹{order.total_amount} order has been paid and will ship soon.", f"/shop/orders/{order.id}")
    return "paid"


IST = timedelta(hours=5, minutes=30)


def next_invoice_number(db: Session) -> str:
    """Next invoice number, consecutive within the Indian financial year
    (April-March, in IST) as GST invoices require: "AV2627-000001". The
    counter row is locked, so two orders paid at once can't share a number."""
    now = utcnow() + IST
    start = now.year if now.month >= 4 else now.year - 1
    fy = f"{start % 100:02d}{(start + 1) % 100:02d}"
    db.execute(pg_insert(ShopInvoiceCounter).values(financial_year=fy, last_number=0).on_conflict_do_nothing())
    counter = db.query(ShopInvoiceCounter).filter(ShopInvoiceCounter.financial_year == fy).with_for_update().one()
    counter.last_number += 1
    return f"AV{fy}-{counter.last_number:06d}"
