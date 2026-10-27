"""Customer return requests after delivery (refund policy, section 2).

    requested -> approved (reverse pickup booked) -> received (checked;
    good items back into stock) -> refunded;   requested -> rejected

- Within the return window (Settings, default 7 days after delivery).
- Products marked non-returnable (henna, hair, skin) only for "damaged" or
  "wrong_item", and those need a photo.
- Refund = what was actually paid for the returned items (their share of
  any coupon discount taken off); delivery/COD charges too when the whole
  order comes back damaged or wrong.
- Prepaid orders are refunded to the original payment (Razorpay, queued);
  COD orders to the customer's UPI ID by hand, recorded with its UTR. Both
  get a GST credit note when the order was invoiced.
"""

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.payment_ops import Refund
from app.models.shipping import Shipment
from app.models.shop import RETURN_REASONS, ReturnRequest, ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.services.notifications import notify, notify_admins
from app.services.platform_settings import get_platform_settings
from app.services.refunds import RefundError, issue_manual_refund, issue_refund
from app.services.shipping import ShippingError, get_provider


class ReturnError(Exception):
    """A return that can't be made (shown to the person as-is)."""


def _money(v: float) -> float:
    return round(v + 1e-9, 2)


def return_window_ends(db: Session, order: ShopOrder):
    if not order.delivered_at:
        return None
    return order.delivered_at + timedelta(days=int(get_platform_settings(db)["shop_return_window_days"]))


def _already_requested(db: Session, order_id) -> dict:
    """order_item_id -> quantity already in open/finished requests."""
    taken: dict = {}
    for req in db.query(ReturnRequest).filter(ReturnRequest.order_id == order_id, ReturnRequest.status != "rejected"):
        for line in req.items:
            taken[line["order_item_id"]] = taken.get(line["order_item_id"], 0) + line["quantity"]
    return taken


def refund_for(order: ShopOrder, items: dict, lines: list[dict], reason: str) -> float:
    """What the customer paid for the returned quantities."""
    items_amount = order.items_amount or sum(i.subtotal for i in items.values()) or 1
    paid_ratio = (items_amount - (order.discount_amount or 0)) / items_amount
    amount = sum(items[line["order_item_id"]].unit_price * line["quantity"] * paid_ratio for line in lines)
    whole_order = all(
        sum(l["quantity"] for l in lines if l["order_item_id"] == key) == item.quantity for key, item in items.items()
    )
    if whole_order and reason in ("damaged", "wrong_item"):
        amount += (order.shipping_fee or 0) + (order.cod_fee or 0)
    return _money(amount)


def create_request(db: Session, order: ShopOrder, user_id, lines: list[dict], reason: str, details: str | None,
                   photo_urls: list[str], refund_upi: str | None) -> ReturnRequest:
    if order.consumer_id != user_id:
        raise ReturnError("Order not found")
    if order.status != "delivered":
        raise ReturnError("Returns can be requested once the order is delivered")
    ends = return_window_ends(db, order)
    if ends and utcnow() > ends:
        raise ReturnError("The return window for this order has closed - contact us if something is wrong")
    if reason not in RETURN_REASONS:
        raise ReturnError("Choose a reason for the return")
    if not lines:
        raise ReturnError("Choose at least one item to return")

    items = {str(i.id): i for i in db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id)}
    taken = _already_requested(db, order.id)
    clean = []
    for line in lines:
        key, qty = str(line.get("order_item_id")), int(line.get("quantity") or 0)
        item = items.get(key)
        if item is None or qty < 1:
            raise ReturnError("One of the items isn't part of this order")
        if qty > item.quantity - taken.get(key, 0):
            raise ReturnError(f"You can return at most {item.quantity - taken.get(key, 0)} of {item.product_name}")
        product = db.get(ShopProduct, item.product_id)
        if product is not None and not product.returnable:
            if reason not in ("damaged", "wrong_item"):
                raise ReturnError(f"{item.product_name} can only be returned if it arrived damaged or wrong (for hygiene reasons)")
            if not photo_urls:
                raise ReturnError("Please add a photo of the damaged or wrong item")
        clean.append({"order_item_id": key, "quantity": qty})
    if reason in ("damaged", "wrong_item") and not photo_urls:
        raise ReturnError("Please add a photo showing the problem")
    if order.payment_method == "cod":
        upi = (refund_upi or "").strip()
        if "@" not in upi or len(upi) < 5:
            raise ReturnError("Enter the UPI ID we should send your refund to")
        refund_upi = upi

    request = ReturnRequest(
        id=uuid.uuid4(), order_id=order.id, consumer_id=user_id, status="requested", reason_code=reason,
        details=(details or "").strip()[:2000] or None, photo_urls=",".join(photo_urls) or None, items=clean,
        refund_amount=refund_for(order, items, clean, reason), refund_upi=refund_upi if order.payment_method == "cod" else None,
    )
    db.add(request)
    from app.services.referrals import on_return_requested

    on_return_requested(db, order)
    notify_admins(db, "Return requested", f"Order {str(order.id)[:8]}: {reason.replace('_', ' ')}, ₹{request.refund_amount:g}.", "/admin")
    return request


def approve(db: Session, request: ReturnRequest, admin_id, pickup: dict) -> Shipment:
    """Approves and books the reverse pickup (manual provider: the admin's
    courier details). Doesn't commit."""
    if request.status != "requested":
        raise ReturnError(f"A {request.status} return can't be approved")
    order = db.get(ShopOrder, request.order_id)
    from app.services.shipping.service import order_package

    provider = get_provider()
    try:
        booking = provider.book_reverse(db, order, order_package(db, order), pickup)
    except ShippingError as exc:
        raise ReturnError(str(exc))
    shipment = Shipment(
        id=uuid.uuid4(), order_id=order.id, direction="reverse", return_request_id=request.id, provider=provider.name,
        awb=booking.awb, courier_name=booking.courier_name, tracking_url=booking.tracking_url, label_url=booking.label_url,
        status="booked", weight_g=order_package(db, order).weight_g, length_cm=20, breadth_cm=15, height_cm=10, cod_amount=0,
        shipping_charge=booking.shipping_charge, pickup_scheduled_at=booking.pickup_scheduled_at, last_event_at=utcnow(),
        raw=booking.raw or None, created_by=admin_id,
    )
    db.add(shipment)
    request.status, request.decided_by, request.decided_at = "approved", admin_id, utcnow()
    request.admin_note = (pickup.get("note") or "")[:300] or None
    pickup_note = f" {booking.courier_name} will collect it" if booking.courier_name else " We'll arrange the pickup"
    notify(db, order.consumer_id, "shop", "Return approved",
           f"Your return is approved.{pickup_note} - please keep the item(s) packed. You'll be refunded ₹{request.refund_amount:g} once we receive them.",
           f"/shop/orders/{order.id}")
    return shipment


def reject(db: Session, request: ReturnRequest, admin_id, note: str) -> None:
    if request.status != "requested":
        raise ReturnError(f"A {request.status} return can't be rejected")
    request.status, request.decided_by, request.decided_at, request.admin_note = "rejected", admin_id, utcnow(), note[:300]
    notify(db, request.consumer_id, "shop", "Return not approved", f"We couldn't accept this return: {note}", f"/shop/orders/{request.order_id}")


def receive(db: Session, request: ReturnRequest, condition: str, admin_id, upi_reference: str | None = None) -> Refund:
    """The returned items are back: restock good ones and refund. COD
    orders need the UTR of the UPI refund the admin has sent."""
    if request.status != "approved":
        raise ReturnError(f"A {request.status} return can't be received")
    if condition not in ("good", "damaged"):
        raise ReturnError("Condition must be good or damaged")
    order = db.get(ShopOrder, request.order_id)
    if order.payment_method == "cod" and not (upi_reference or "").strip():
        raise ReturnError(f"Send ₹{request.refund_amount:g} to {request.refund_upi} and enter the UPI reference (UTR)")

    if condition == "good":
        for line in request.items:
            item = db.get(ShopOrderItem, uuid.UUID(line["order_item_id"]))
            row = db.get(ShopProductVariant, item.variant_id) if item.variant_id else db.get(ShopProduct, item.product_id)
            if row is not None:
                row.stock_quantity += line["quantity"]
    reverse = db.query(Shipment).filter(Shipment.return_request_id == request.id).first()
    if reverse and reverse.status not in ("delivered", "cancelled"):
        reverse.status, reverse.delivered_at = "delivered", utcnow()

    reason = f"Return ({request.reason_code.replace('_', ' ')}), received {condition}"
    try:
        if order.payment_method == "online":
            refund = issue_refund(db, target_type="shop_order", target_id=order.id, payment_id=order.razorpay_payment_id,
                                  amount=request.refund_amount, reason=reason, initiated_by=admin_id, refundable=order.amount_paid)
        else:
            refund = issue_manual_refund(db, target_type="shop_order", target_id=order.id, amount=request.refund_amount,
                                         reference=upi_reference.strip(), reason=reason, initiated_by=admin_id)
    except RefundError as exc:
        raise ReturnError(str(exc))
    request.status, request.condition, request.received_at, request.refund_id = "received", condition, utcnow(), refund.id
    if refund.status == "processed":
        request.status = "refunded"
    return refund


def on_refund_processed(db: Session, refund: Refund) -> None:
    """Called when a refund completes: closes the return it belongs to."""
    request = db.query(ReturnRequest).filter(ReturnRequest.refund_id == refund.id).first()
    if request is not None and request.status == "received":
        request.status = "refunded"
