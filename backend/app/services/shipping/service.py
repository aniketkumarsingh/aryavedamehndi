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
from app.services.shipping import NDR_ACTIONS, Package, Serviceability, ShippingError, TrackingUpdate, get_provider
from app.services.shop_orders import mark_delivered, mark_returned, mark_shipped

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


def update_details(db: Session, shipment: Shipment, courier_name: str | None, awb: str | None, tracking_url: str | None,
                   shipping_charge: float | None = None) -> None:
    """Admin correction of the courier details (manual provider), kept in
    step on the order; and the courier's charge once billed."""
    if shipping_charge is not None:
        shipment.shipping_charge = round(shipping_charge, 2)
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
    if shipment.status == "ndr" and update.status != "ndr" and shipment.ndr_status in ("open", "answered", "auto"):
        shipment.ndr_status = "closed"  # delivery moved on after the failed attempt
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
        shipment.ndr_status, shipment.ndr_action, shipment.ndr_raised_at = "open", None, update.occurred_at
        shipment.ndr_attempts = (shipment.ndr_attempts or 0) + 1
        shipment.ndr_note = (update.description or "")[:300] or None
        notify(db, order.consumer_id, "shop", "Delivery attempt failed",
               f"The courier couldn't deliver your order{reason}. Choose what to do: try again, change the address, or cancel - "
               "if we don't hear from you in 24 hours we'll ask them to try again.", link)
        notify_admins(db, "Failed delivery attempt", f"Order {str(order.id)[:8]} ({shipment.courier_name or 'courier'} {shipment.awb or ''}){reason}.", "/admin")
    elif update.status == "rto":
        notify_admins(db, "Parcel returning", f"Order {str(order.id)[:8]} is being returned to us by {shipment.courier_name or 'the courier'}.", "/admin")
    elif update.status == "rto_delivered":
        notify_admins(db, "Returned parcel received", f"Order {str(order.id)[:8]} is back with us - check its condition and confirm the return in Admin → Shipping.", "/admin")


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


# ------------------------------------------------------- failed deliveries --

def respond_to_ndr(db: Session, shipment: Shipment, action: str, details: dict, by: str) -> None:
    """The customer (or an admin, or the 24-hour rule) decides what happens
    after a failed attempt. `by` is "customer", "admin" or "auto"."""
    if action not in NDR_ACTIONS:
        raise ShippingError("Choose reattempt, change_address or cancel")
    # The customer answers once; an admin can still change course after that.
    allowed = ("open", "answered") if by == "admin" else ("open",)
    if shipment.status != "ndr" or shipment.ndr_status not in allowed:
        raise ShippingError("There's no failed delivery waiting for an answer")
    order = db.get(ShopOrder, shipment.order_id)
    note = ""
    if action == "change_address":
        address, pincode, phone = (details.get("address") or "").strip(), (details.get("pincode") or "").strip(), (details.get("phone") or "").strip()
        if not address or not valid_pincode(pincode):
            raise ShippingError("Enter the new address and a valid 6-digit PIN code")
        answer = check_serviceability(db, pincode, cod=order.payment_method == "cod")
        if not answer.deliverable or (order.payment_method == "cod" and not answer.cod_available):
            raise ShippingError(f"We can't deliver this order to PIN code {pincode}")
        note = f"Address changed (was: {order.shipping_address}, {order.shipping_pincode})"
        order.shipping_address, order.shipping_pincode = address[:2000], pincode
        if phone:
            order.shipping_phone = phone[:15]
    get_provider(shipment.provider).ndr_action(shipment.awb or "", action, {
        "address": order.shipping_address, "pincode": order.shipping_pincode, "phone": order.shipping_phone,
        "preferred_date": details.get("preferred_date"),
    })
    shipment.ndr_status = "auto" if by == "auto" else "answered"
    shipment.ndr_action = action
    label = {"reattempt": "Try delivering again", "change_address": "Deliver to a new address", "cancel": "Cancel and return to us"}[action]
    _store_event(db, shipment, "ndr", f"{label} (requested by {by})" + (f" - {note}" if note else ""), None, utcnow(), "system",
                 f"ndr-response:{shipment.ndr_attempts}:{action}:{by}")
    if action == "cancel":
        notify(db, order.consumer_id, "shop", "Delivery cancelled",
               "We've asked the courier to return your parcel." + (" Your payment will be refunded once it's back with us." if order.payment_method == "online" else ""),
               f"/shop/orders/{order.id}")
    if shipment.provider == "manual" or by != "auto":
        notify_admins(db, "Failed delivery: action needed" if shipment.provider == "manual" else "Failed delivery answered",
                      f"Order {str(order.id)[:8]}: {label.lower()} ({by}). " + ("Pass this on to the courier." if shipment.provider == "manual" else ""), "/admin")


@job_handler("shipping.ndr_auto")
def ndr_auto_reattempt(db: Session, payload: dict) -> str:
    """Failed deliveries nobody answered within 24 hours get one reattempt."""
    cutoff = utcnow() - timedelta(hours=24)
    waiting = (
        db.query(Shipment)
        .filter(Shipment.status == "ndr", Shipment.ndr_status == "open", Shipment.ndr_raised_at < cutoff)
        .with_for_update(skip_locked=True)
        .all()
    )
    for shipment in waiting:
        respond_to_ndr(db, shipment, "reattempt", {}, by="auto")
    return f"{len(waiting)} reattempts requested"


periodic("shipping.ndr_auto", timedelta(hours=1))


# ------------------------------------------------------------ returns (RTO) --

def receive_return(db: Session, shipment: Shipment, condition: str, note: str | None, admin_id) -> None:
    """Admin confirms a returned parcel is back and what state it's in:
    good -> back into stock; damaged -> written off. Prepaid orders are then
    refunded (with a credit note) via the payments refund path."""
    if condition not in ("good", "damaged"):
        raise ShippingError("Condition must be good or damaged")
    if shipment.status not in ("rto", "rto_delivered", "ndr", "in_transit", "out_for_delivery", "picked_up", "booked"):
        raise ShippingError(f"A {shipment.status} shipment can't be received back")
    order = db.get(ShopOrder, shipment.order_id)
    if order.status != "shipped":
        raise ShippingError(f"A {order.status} order can't be marked returned")
    if shipment.status != "rto_delivered":
        _store_event(db, shipment, "rto_delivered", "Received back at our warehouse", None, utcnow(), "system", f"rto-received:{shipment.id}")
        shipment.status = "rto_delivered"
    if shipment.ndr_status in ("open", "answered", "auto"):
        shipment.ndr_status = "closed"
    reason = f"Parcel returned ({condition})" + (f": {note}" if note else "")
    mark_returned(db, order, reason, initiated_by=admin_id, condition=condition)


# ---------------------------------------------------------- COD remittance --

def record_cod_remittance(db: Session, shipments: list[Shipment], reference: str, remitted_at=None) -> int:
    """Marks COD parcels as paid over by the courier: the order's money is
    now ours (payment status cod_collected). Returns how many changed."""
    remitted_at = remitted_at or utcnow()
    changed = 0
    for shipment in shipments:
        if not shipment.cod_amount or shipment.cod_remitted_at:
            continue
        if shipment.status != "delivered":
            raise ShippingError(f"Shipment {shipment.awb or shipment.id} isn't delivered yet")
        shipment.cod_remitted_at, shipment.cod_remittance_ref = remitted_at, reference[:80]
        order = db.get(ShopOrder, shipment.order_id)
        if order.payment_status in ("cod_with_courier", "cod_due"):
            order.payment_status, order.amount_paid, order.paid_at = "cod_collected", order.total_amount, remitted_at
        changed += 1
    return changed


def unremitted_cod(db: Session, older_than_days: int = 10) -> list[Shipment]:
    cutoff = utcnow() - timedelta(days=older_than_days)
    return (
        db.query(Shipment)
        .filter(Shipment.cod_amount > 0, Shipment.status == "delivered", Shipment.cod_remitted_at.is_(None), Shipment.delivered_at < cutoff)
        .order_by(Shipment.delivered_at)
        .all()
    )


@job_handler("shipping.cod_remittance_sync")
def sync_cod_remittances(db: Session, payload: dict) -> str:
    """For couriers that report payouts: match them to parcels by AWB."""
    provider = get_provider()
    remittances = provider.cod_remittances(utcnow() - timedelta(days=30))
    applied = 0
    for r in remittances:
        shipment = db.query(Shipment).filter(Shipment.provider == provider.name, Shipment.awb == r.awb).with_for_update().first()
        if shipment and not shipment.cod_remitted_at and shipment.status == "delivered":
            applied += record_cod_remittance(db, [shipment], r.reference, r.remitted_at)
    return f"{applied} remittances recorded"


periodic("shipping.cod_remittance_sync", timedelta(hours=6))


# ------------------------------------------------------------------ report --

def shipping_report(db: Session, months: int = 6) -> list[dict]:
    """Per month (IST): parcels, delivery + COD fees we charged customers,
    what couriers charged us, and the difference."""
    from collections import defaultdict

    since = utcnow() - timedelta(days=31 * months)
    rows = defaultdict(lambda: {"parcels": 0, "fees_collected": 0.0, "courier_charges": 0.0, "parcels_without_charge": 0})
    for shipment, order in (
        db.query(Shipment, ShopOrder).join(ShopOrder, ShopOrder.id == Shipment.order_id)
        .filter(Shipment.created_at >= since, Shipment.status != "cancelled").all()
    ):
        month = f"{shipment.created_at + IST:%Y-%m}"
        row = rows[month]
        row["parcels"] += 1
        row["fees_collected"] += (order.shipping_fee or 0) + (order.cod_fee or 0)
        if shipment.shipping_charge is None:
            row["parcels_without_charge"] += 1
        else:
            row["courier_charges"] += shipment.shipping_charge
    report = []
    for month in sorted(rows, reverse=True):
        r = rows[month]
        report.append({"month": month, **{k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()},
                       "margin": round(r["fees_collected"] - r["courier_charges"], 2)})
    return report
