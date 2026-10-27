"""Server-side conversions: Meta Conversions API and the GA4 Measurement
Protocol, for purchases the browser pixel can miss (ad blockers, a closed
tab after paying, Cash on Delivery).

Only for customers who accepted analytics cookies (users.analytics_consent).
The event id is the order id - the same one the browser sends - so each
platform counts a purchase once. Each (event, platform) is recorded in
conversion_events and never sent twice. Off unless the keys are set:
META_PIXEL_ID + META_CAPI_TOKEN, GA4_MEASUREMENT_ID + GA4_API_SECRET.
"""

import hashlib
import time
import uuid

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.growth import ConversionEvent
from app.models.shop import ShopOrder, ShopOrderItem
from app.models.user import User
from app.services.jobs import enqueue, job_handler

settings = get_settings()
META_URL = "https://graph.facebook.com/v21.0/{pixel}/events"
GA4_URL = "https://www.google-analytics.com/mp/collect"


def _sha(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def enabled() -> dict:
    return {
        "meta": bool(settings.meta_pixel_id and settings.meta_capi_token),
        "ga4": bool(settings.ga4_measurement_id and settings.ga4_api_secret),
    }


def queue_purchase(db: Session, order: ShopOrder) -> None:
    """Called when an order is confirmed (paid online or COD placed)."""
    user = db.get(User, order.consumer_id)
    if user is None or not user.analytics_consent or not any(enabled().values()):
        return
    enqueue(db, "conversions.purchase", {"order_id": str(order.id)}, dedupe_key=f"conversion-purchase:{order.id}")


def _record(db: Session, event_id: str, platform: str, name: str, status: str, detail: str = "") -> bool:
    """Claims the (event, platform) slot; False if it was already used."""
    try:
        with db.begin_nested():
            db.add(ConversionEvent(id=uuid.uuid4(), event_id=event_id, platform=platform, event_name=name, status=status, detail=detail[:300]))
            db.flush()
        return True
    except IntegrityError:
        return False


def _meta_payload(order: ShopOrder, user: User, items: list[ShopOrderItem]) -> dict:
    a = order.attribution or user.attribution or {}
    user_data = {"external_id": [_sha(str(user.id))]}
    if user.phone:
        digits = "".join(c for c in user.phone if c.isdigit())
        user_data["ph"] = [_sha(digits if len(digits) > 10 else f"91{digits}")]
    if order.contact_email:
        user_data["em"] = [_sha(order.contact_email)]
    if order.shipping_pincode:
        user_data["zp"] = [_sha(order.shipping_pincode)]
    user_data["country"] = [_sha("in")]
    if a.get("fbp"):
        user_data["fbp"] = a["fbp"]
    if a.get("fbc"):
        user_data["fbc"] = a["fbc"]
    elif a.get("fbclid"):
        user_data["fbc"] = f"fb.1.{int(time.time() * 1000)}.{a['fbclid']}"
    return {
        "data": [{
            "event_name": "Purchase",
            "event_time": int(order.confirmed_at.timestamp()) if order.confirmed_at else int(time.time()),
            "event_id": str(order.id),
            "action_source": "website",
            "event_source_url": f"{settings.public_site_url.rstrip('/')}/cart",
            "user_data": user_data,
            "custom_data": {
                "currency": "INR",
                "value": order.total_amount,
                "order_id": str(order.id),
                "content_type": "product",
                "content_ids": [str(i.variant_id or i.product_id) for i in items],
                "num_items": sum(i.quantity for i in items),
            },
        }],
    }


def _ga4_payload(order: ShopOrder, user: User, items: list[ShopOrderItem]) -> dict:
    a = order.attribution or user.attribution or {}
    return {
        # Without the browser's _ga id the hit still counts, as a new client.
        "client_id": a.get("ga_client_id") or f"{uuid.UUID(str(user.id)).int % 10**10}.{int(user.created_at.timestamp()) if user.created_at else 0}",
        "user_id": str(user.id),
        "events": [{
            "name": "purchase",
            "params": {
                "transaction_id": str(order.id),
                "currency": "INR",
                "value": order.total_amount,
                "shipping": order.shipping_fee,
                "coupon": order.coupon_code or "",
                "items": [{"item_id": str(i.variant_id or i.product_id), "item_name": i.product_name, "price": i.unit_price,
                           "quantity": i.quantity} for i in items],
            },
        }],
    }


@job_handler("conversions.purchase")
def send_purchase(db: Session, payload: dict) -> str:
    order = db.get(ShopOrder, uuid.UUID(payload["order_id"]))
    if order is None:
        return "order gone"
    user = db.get(User, order.consumer_id)
    if user is None or not user.analytics_consent:
        return "no consent"
    items = db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id).all()
    results = []
    with httpx.Client(timeout=10) as client:
        for platform, on in enabled().items():
            if not on or db.query(ConversionEvent.id).filter_by(event_id=str(order.id), platform=platform, event_name="purchase").first():
                continue
            if platform == "meta":
                res = client.post(META_URL.format(pixel=settings.meta_pixel_id), params={"access_token": settings.meta_capi_token},
                                  json=_meta_payload(order, user, items))
            else:
                res = client.post(GA4_URL, params={"measurement_id": settings.ga4_measurement_id, "api_secret": settings.ga4_api_secret},
                                  json=_ga4_payload(order, user, items))
            res.raise_for_status()  # failures retry with backoff (job queue)
            _record(db, str(order.id), platform, "purchase", "sent")
            results.append(platform)
    return "sent: " + (", ".join(results) or "nothing new")
