"""Shipping business rules, independent of the courier.

- check_serviceability: can we deliver to a PIN code, with COD, and when
  (provider answers cached for 24 h; the manual provider reads settings).
- order_package: weight and box size from the items' packed sizes.
- book_shipment: books with the provider, records the shipment, then moves
  the order to shipped and issues the GST invoice (shop_orders.mark_shipped).
- apply_update: records one tracking scan (each stored once) and moves the
  shipment forward; delivered/out-for-delivery/failed attempt/return each
  notify the right people and drive the order.
- Courier webhooks are stored then processed in the worker; a poll every
  2 hours catches scans a webhook missed (live providers only).
"""

import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.shipping import (
    TERMINAL_SHIPMENT_STATUSES,
    PincodeServiceability,
    Shipment,
    ShipmentEvent,
    ShippingWebhookEvent,
)
from app.models.shop import ShopOrder, ShopOrderItem, ShopProduct, ShopProductVariant
from app.services.jobs import enqueue, job_handler, periodic
from app.services.notifications import notify, notify_admins
from app.services.platform_settings import get_platform_settings
from app.services.shipping import Package, Serviceability, ShippingError, TrackingUpdate, get_provider
from app.services.shop_orders import mark_delivered, mark_shipped

log = logging.getLogger(__name__)
CACHE_FOR = timedelta(hours=24)
IST = timedelta(hours=5, minutes=30)

# How far along each status is. A scan only moves a shipment forward, except
# that after a failed attempt (ndr) the courier tries again.
RANK = {"booked": 0, "picked_up": 1, "in_transit": 2, "ndr": 3, "out_for_delivery": 4, "delivered": 5, "rto": 6, "rto_delivered": 7, "cancelled": 8}


def valid_pincode(pincode: str | None) -> bool:
    return bool(pincode) and len(pincode) == 6 and pincode.isdigit() and pincode[0] != "0"


# ---------------------------------------------------------- serviceability --

def check_serviceability(db: Session, pincode: str, cod: bool = False, package: Package | None = None) -> Serviceability:
    if not valid_pincode(pincode):
        return Serviceability(deliverable=False, cod_available=False)
    provider = get_provider()
    if provider.name == "manual":  # reads live settings - nothing to cache
        return provider.serviceability(db, pincode, cod, package)

    cached = db.get(PincodeServiceability, (pincode, provider.name))
    if cached and cached.checked_at > utcnow() - CACHE_FOR:
        return Serviceability(cached.deliverable, cached.cod_available, cached.eta_min_days, cached.eta_max_days)
    answer = provider.serviceability(db, pincode, cod, package)
    db.execute(
        pg_insert(PincodeServiceability)
        .values(pincode=pincode, provider=provider.name, deliverable=answer.deliverable, cod_available=answer.cod_available,
                eta_min_days=answer.eta_min_days, eta_max_days=answer.eta_max_days, checked_at=utcnow())
        .on_conflict_do_update(
            index_elements=["pincode", "provider"],
            set_={"deliverable": answer.deliverable, "cod_available": answer.cod_available, "eta_min_days": answer.eta_min_days,
                  "eta_max_days": answer.eta_max_days, "checked_at": utcnow()},
        )
    )
    return answer


def delivery_window(answer: Serviceability, now=None) -> tuple[str, str] | None:
    """Estimated delivery dates (IST) for display, e.g. ("29 Oct", "2 Nov")."""
    if answer.eta_min_days is None or answer.eta_max_days is None:
        return None
    today = (now or utcnow()) + IST
    first, last = today + timedelta(days=answer.eta_min_days), today + timedelta(days=answer.eta_max_days)
    return f"{first.day} {first:%b}", f"{last.day} {last:%b}"


# ----------------------------------------------------------------- package --

def order_package(db: Session, order: ShopOrder) -> Package:
    """Packed weight = items + packaging. The box is the larger of the
    minimum box and the largest item on each side."""
    s = get_platform_settings(db)
    default_item = int(s["shop_default_item_weight_g"])
    weight = int(s["shop_packaging_weight_g"])
    length, breadth, height = float(s["shop_box_length_cm"]), float(s["shop_box_breadth_cm"]), float(s["shop_box_height_cm"])
    for item in db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id):
        source = db.get(ShopProductVariant, item.variant_id) if item.variant_id else None
        product = db.get(ShopProduct, item.product_id)
        unit_weight = (source and source.weight_g) or (product and product.weight_g) or default_item
        weight += unit_weight * item.quantity
        for row in (source, product):
            if row and row.length_cm:
                length, breadth, height = max(length, row.length_cm), max(breadth, row.breadth_cm or 0), max(height, row.height_cm or 0)
                break
    return Package(weight_g=weight, length_cm=length, breadth_cm=breadth, height_cm=height)


# ----------------------------------------------------------------- booking --

def active_shipment(db: Session, order_id) -> Shipment | None:
    return (
        db.query(Shipment)
        .filter(Shipment.order_id == order_id, Shipment.status.notin_(("cancelled",)))
        .order_by(Shipment.created_at.desc())
        .first()
    )


def book_shipment(db: Session, order: ShopOrder, details: dict, created_by=None) -> Shipment:
    """Books the courier for a confirmed order and ships it. Doesn't commit."""
    if order.status != "confirmed":
        raise ShippingError(f"A {order.status} order can't be shipped")
    if active_shipment(db, order.id):
        raise ShippingError("This order already has a shipment")
    if order.shipping_pincode:
        answer = check_serviceability(db, order.shipping_pincode, cod=order.payment_method == "cod")
        if not answer.deliverable:
            raise ShippingError(f"We can't deliver to PIN code {order.shipping_pincode}")
        if order.payment_method == "cod" and not answer.cod_available:
            raise ShippingError(f"Cash on Delivery isn't available at PIN code {order.shipping_pincode}")

    package = order_package(db, order)
    provider = get_provider()
    booking = provider.book(db, order, package, details)
    shipment = Shipment(
        id=uuid.uuid4(),
        order_id=order.id,
        provider=provider.name,
        awb=booking.awb,
        courier_name=booking.courier_name,
        tracking_url=booking.tracking_url,
        label_url=booking.label_url,
        status="booked",
        weight_g=package.weight_g,
        length_cm=package.length_cm,
        breadth_cm=package.breadth_cm,
        height_cm=package.height_cm,
        cod_amount=order.total_amount if order.payment_method == "cod" else 0,
        shipping_charge=booking.shipping_charge,
        pickup_scheduled_at=booking.pickup_scheduled_at,
        last_event_at=utcnow(),
        raw=booking.raw or None,
        created_by=created_by,
    )
    db.add(shipment)
    db.flush()
    _store_event(db, shipment, "booked", "Shipment booked" + (f" with {booking.courier_name}" if booking.courier_name else ""), None, utcnow(), "system", "booked")
    mark_shipped(db, order, booking.courier_name, booking.awb, booking.tracking_url)
    return shipment


def update_details(db: Session, shipment: Shipment, courier_name: str | None, awb: str | None, tracking_url: str | None) -> None:
    """Admin correction of the courier details (manual provider), kept in
    step on the order."""
    if courier_name is not None:
        shipment.courier_name = courier_name.strip() or shipment.courier_name
    if awb is not None:
        shipment.awb = awb.strip() or None
    if tracking_url is not None:
        shipment.tracking_url = tracking_url.strip() or None
    order = db.get(ShopOrder, shipment.order_id)
    order.courier_name, order.tracking_number, order.tracking_url = shipment.courier_name, shipment.awb, shipment.tracking_url


# ---------------------------------------------------------------- tracking --

def _store_event(db, shipment, status, description, location, occurred_at, source, external_id, raw=None) -> bool:
    inserted = db.execute(
        pg_insert(ShipmentEvent)
        .values(id=uuid.uuid4(), shipment_id=shipment.id, status=status, description=(description or "")[:300] or None,
                location=(location or "")[:120] or None, occurred_at=occurred_at, source=source, external_id=external_id[:160],
                raw=raw, created_at=utcnow())
        .on_conflict_do_nothing(constraint="uq_shipment_events_external")
        .returning(ShipmentEvent.id)
    ).first()
    return inserted is not None


def _moves_forward(current: str, new: str) -> bool:
    if current in TERMINAL_SHIPMENT_STATUSES:
        return False
    if current == "ndr" and new in ("in_transit", "out_for_delivery"):
        return True  # re-attempt after a failed delivery
    return RANK[new] > RANK[current]


def apply_update(db: Session, shipment: Shipment, update: TrackingUpdate, source: str) -> bool:
    """Records one scan; returns False if it was already recorded. Moves the
    shipment (and order) forward when the scan is newer progress."""
    if update.status not in RANK:
        raise ShippingError(f"Unknown shipment status {update.status!r}")
    if not _store_event(db, shipment, update.status, update.description, update.location, update.occurred_at, source, update.external_id, update.raw):
        return False
    stale = shipment.last_event_at and update.occurred_at < shipment.last_event_at - timedelta(minutes=1)
    if stale or not _moves_forward(shipment.status, update.status):
        return True
    shipment.status = update.status
    shipment.last_event_at = max(update.occurred_at, shipment.last_event_at or update.occurred_at)
    _on_status(db, shipment, update)
    return True


def _on_status(db: Session, shipment: Shipment, update: TrackingUpdate) -> None:
    order = db.get(ShopOrder, shipment.order_id)
    link = f"/shop/orders/{order.id}"
    if update.status == "out_for_delivery":
        cod = f" Please keep ₹{shipment.cod_amount:g} ready." if shipment.cod_amount else ""
        notify(db, order.consumer_id, "shop", "Out for delivery", f"Your order is out for delivery today.{cod}", link)
        enqueue(db, "email.shop_out_for_delivery", {"order_id": str(order.id)}, dedupe_key=f"email-ofd:{shipment.id}")
    elif update.status == "delivered":
        shipment.delivered_at = update.occurred_at
        if order.status == "shipped":
            mark_delivered(db, order)
            order.delivered_at = update.occurred_at
    elif update.status == "ndr":
        reason = f" ({update.description})" if update.description else ""
        notify(db, order.consumer_id, "shop", "Delivery attempt failed",
               f"The courier couldn't deliver your order{reason}. They'll try again - check your phone is reachable, or contact us to change the address.", link)
        notify_admins(db, "Failed delivery attempt", f"Order {str(order.id)[:8]} ({shipment.courier_name or 'courier'} {shipment.awb or ''}){reason}.", "/admin")
    elif update.status == "rto":
        notify_admins(db, "Parcel returning", f"Order {str(order.id)[:8]} is being returned to us by {shipment.courier_name or 'the courier'}.", "/admin")
    elif update.status == "rto_delivered":
        notify_admins(db, "Returned parcel received", f"Order {str(order.id)[:8]} is back with us - check it and mark the order returned.", "/admin")


def record_manual_update(db: Session, shipment: Shipment, status: str, description: str | None, location: str | None) -> bool:
    update = TrackingUpdate(awb=shipment.awb or "", status=status, occurred_at=utcnow(), external_id=f"manual:{uuid.uuid4()}",
                            description=description, location=location)
    return apply_update(db, shipment, update, "manual")


def shipments_for(db: Session, order_id) -> list[tuple[Shipment, list[ShipmentEvent]]]:
    shipments = db.query(Shipment).filter(Shipment.order_id == order_id).order_by(Shipment.created_at).all()
    return [
        (s, db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id == s.id).order_by(ShipmentEvent.occurred_at, ShipmentEvent.created_at).all())
        for s in shipments
    ]


# ------------------------------------------------------- webhooks & polling --

def record_webhook(db: Session, provider_name: str, headers: dict, body: bytes) -> str:
    """Verifies (via the provider), stores and queues a courier webhook.
    Returns "queued" or "duplicate". Doesn't commit."""
    provider = get_provider(provider_name)
    event_key = provider.verify_webhook(headers, body)  # raises ValueError / WebhookNotSupported
    row_id = uuid.uuid4()
    inserted = db.execute(
        pg_insert(ShippingWebhookEvent)
        .values(id=row_id, provider=provider_name, event_key=f"{provider_name}:{event_key}"[:160], payload=json.loads(body),
                status="received", received_at=utcnow())
        .on_conflict_do_nothing(index_elements=["event_key"])
        .returning(ShippingWebhookEvent.id)
    ).first()
    if not inserted:
        return "duplicate"
    enqueue(db, "shipping.process_webhook", {"event_row_id": str(row_id)}, dedupe_key=f"ship-event:{row_id}")
    return "queued"


@job_handler("shipping.process_webhook")
def process_webhook(db: Session, payload: dict) -> str:
    event = db.get(ShippingWebhookEvent, uuid.UUID(payload["event_row_id"]), with_for_update=True)
    if event is None or event.status != "received":
        return "already processed"
    updates = get_provider(event.provider).parse_updates(event.payload)
    applied = 0
    for update in updates:
        shipment = db.query(Shipment).filter(Shipment.provider == event.provider, Shipment.awb == update.awb).with_for_update().first()
        if shipment and apply_update(db, shipment, update, "webhook"):
            applied += 1
    event.status, event.result, event.processed_at = "processed", f"{applied}/{len(updates)} scans applied", utcnow()
    return event.result


@job_handler("shipping.poll")
def poll_tracking(db: Session, payload: dict) -> str:
    provider = get_provider()
    if not provider.live_tracking:
        return "skipped (provider has no live tracking)"
    active = (
        db.query(Shipment)
        .filter(Shipment.provider == provider.name, Shipment.awb.isnot(None), Shipment.status.notin_(TERMINAL_SHIPMENT_STATUSES))
        .all()
    )
    applied = 0
    for shipment in active:
        try:
            for update in provider.track(shipment.awb):
                applied += apply_update(db, shipment, update, "poll")
        except Exception:  # noqa: BLE001 - one bad AWB mustn't stop the rest
            log.exception("tracking poll failed for %s", shipment.awb)
    return f"{len(active)} checked, {applied} new scans"


periodic("shipping.poll", timedelta(hours=2))
