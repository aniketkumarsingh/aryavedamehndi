"""Bringing people back: abandoned-cart reminders and occasion nudges.

growth.abandoned_cart (every 15 min) - a logged-in shopper's cart with
items, untouched for 2 hours: first reminder; still untouched 24 hours
after that: second reminder with a personal one-time coupon (Settings:
percent off, 72 h validity); then it stops. Editing the cart starts the
sequence afresh. In-app reminders go to everyone; WhatsApp only to people
who opted in to marketing. An order placed while reminders are running is
tagged source="abandoned_cart".

growth.occasions (daily, 10:00 IST) - for each active occasion whose send
day has come (date minus lead days), every past customer who opted in and
had a completed booking gets one nudge with their last artist's page.
"""

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import utcnow
from app.models.booking import Booking
from app.models.growth import CampaignSend, Cart, Occasion
from app.models.shop import ShopCoupon, ShopProduct
from app.models.user import ArtistProfile, User
from app.services.jobs import job_handler, periodic
from app.services.messaging import send_template
from app.services.notifications import notify
from app.services.platform_settings import get_platform_settings

settings = get_settings()
IST = timedelta(hours=5, minutes=30)
FIRST_REMINDER_AFTER = timedelta(hours=2)
SECOND_REMINDER_AFTER = timedelta(hours=24)
RECOVERY_WINDOW = timedelta(days=7)
MAX_LINES = 20


class CartError(Exception):
    pass


def _clean_items(items: list) -> list[dict]:
    if not isinstance(items, list) or len(items) > MAX_LINES:
        raise CartError(f"A cart holds up to {MAX_LINES} lines")
    clean = []
    for line in items:
        try:
            qty = int(line.get("quantity", 0))
            product_id = str(uuid.UUID(str(line["product_id"])))
            variant_id = str(uuid.UUID(str(line["variant_id"]))) if line.get("variant_id") else None
        except (KeyError, TypeError, ValueError):
            raise CartError("Each cart line needs a product and a quantity")
        if 1 <= qty <= 50:
            clean.append({"product_id": product_id, "variant_id": variant_id, "quantity": qty})
    return clean


def save_cart(db: Session, user_id, items: list) -> Cart:
    clean = _clean_items(items)
    cart = db.get(Cart, user_id)
    if cart is None:
        cart = Cart(user_id=user_id, items=[], reminder_stage=0)
        db.add(cart)
    if clean != cart.items:
        cart.items, cart.updated_at, cart.reminder_stage = clean, utcnow(), 0  # active again: fresh sequence
    return cart


def close_cart_for_order(db: Session, user_id, order) -> None:
    """The cart became an order: clear it, and credit the reminder if one
    brought them back."""
    cart = db.get(Cart, user_id)
    if cart is None:
        return
    if cart.reminder_stage > 0 and cart.last_reminded_at and utcnow() - cart.last_reminded_at < RECOVERY_WINDOW:
        order.source = "abandoned_cart"
    cart.items, cart.reminder_stage, cart.updated_at = [], 0, utcnow()


def _personal_coupon(db: Session, user_id, percent: float) -> ShopCoupon:
    code = f"COMEBACK-{secrets.token_hex(3).upper()}"
    coupon = ShopCoupon(code=code, description="Abandoned-cart reminder", discount_type="percent", discount_value=percent,
                        max_discount=None, min_order_amount=0, starts_at=utcnow(), expires_at=utcnow() + timedelta(hours=72),
                        usage_limit=1, per_user_limit=1, user_id=user_id, is_active=True)
    db.add(coupon)
    return coupon


def _live_items(db: Session, cart: Cart) -> bool:
    ids = [uuid.UUID(line["product_id"]) for line in cart.items]
    return bool(ids) and db.query(ShopProduct).filter(ShopProduct.id.in_(ids), ShopProduct.is_active.is_(True)).count() > 0


@job_handler("growth.abandoned_cart")
def abandoned_cart_job(db: Session, payload: dict) -> str:
    now = utcnow()
    percent = float(get_platform_settings(db)["growth_cart_coupon_percent"])
    link = f"{settings.public_site_url.rstrip('/')}/cart"
    first = second = 0
    carts = (
        db.query(Cart)
        .filter(func.jsonb_array_length(Cart.items) > 0, Cart.reminder_stage < 2)
        .with_for_update(skip_locked=True)
        .all()
    )
    for cart in carts:
        user = db.get(User, cart.user_id)
        if user is None or not user.is_active or not _live_items(db, cart):
            continue
        if cart.reminder_stage == 0 and now - cart.updated_at >= FIRST_REMINDER_AFTER:
            notify(db, user.id, "shop", "Still thinking it over?", "Your cart is saved - finish your order whenever you're ready.", "/cart")
            send_template(db, user, "cart_reminder", {"name": (user.name or "there").split(" ")[0], "link": link})
            cart.reminder_stage, cart.last_reminded_at = 1, now
            first += 1
        elif cart.reminder_stage == 1 and cart.last_reminded_at and now - cart.last_reminded_at >= SECOND_REMINDER_AFTER:
            if percent <= 0:  # coupon switched off in Settings: a plain last nudge
                notify(db, user.id, "shop", "Your cart is waiting", "The items you picked are still in your cart.", "/cart")
                send_template(db, user, "cart_reminder", {"name": (user.name or "there").split(" ")[0], "link": link})
                cart.reminder_stage, cart.last_reminded_at = 2, now
                second += 1
                continue
            coupon = _personal_coupon(db, user.id, percent)
            notify(db, user.id, "shop", f"{percent:g}% off your cart",
                   f"Use code {coupon.code} in the next 72 hours for {percent:g}% off the items in your cart.", "/cart")
            send_template(db, user, "cart_reminder_coupon",
                          {"name": (user.name or "there").split(" ")[0], "coupon": coupon.code, "percent": f"{percent:g}", "link": link})
            cart.reminder_stage, cart.last_reminded_at, cart.coupon_code = 2, now, coupon.code
            second += 1
    db.flush()
    return f"{first} first reminders, {second} coupon reminders"


periodic("growth.abandoned_cart", timedelta(minutes=15))


# ---------------------------------------------------------------- occasions --

def _last_artist(db: Session, user_id) -> ArtistProfile | None:
    booking = (
        db.query(Booking).filter(Booking.consumer_id == user_id, Booking.status == "completed")
        .order_by(Booking.scheduled_at.desc()).first()
    )
    return db.get(ArtistProfile, booking.artist_id) if booking else None


def run_occasion(db: Session, occasion: Occasion) -> int:
    """Sends one occasion's nudges; each customer at most once."""
    past_customers = (
        db.query(User).join(Booking, Booking.consumer_id == User.id)
        .filter(Booking.status == "completed", User.is_active.is_(True), User.marketing_opt_in.is_(True))
        .distinct().all()
    )
    already = {row.user_id for row in db.query(CampaignSend.user_id).filter(CampaignSend.occasion_id == occasion.id)}
    sent = 0
    for user in past_customers:
        if user.id in already:
            continue
        artist = _last_artist(db, user.id)
        artist_user = db.get(User, artist.user_id) if artist else None
        artist_name = (artist_user.name if artist_user else None) or "your artist"
        path = f"/artists/{artist.slug}" if artist and artist.slug else "/discover"
        extra = f" {occasion.message}" if occasion.message else ""
        notify(db, user.id, "booking", f"{occasion.name} is coming up",
               f"Book {artist_name} again for {occasion.name} ({occasion.occasion_date:%d %b}) before slots fill up.{extra}", path)
        channels = ["app"]
        if send_template(db, user, "occasion_nudge", {"name": (user.name or "there").split(" ")[0], "occasion": occasion.name,
                                                      "artist": artist_name, "link": settings.public_site_url.rstrip("/") + path}):
            channels.append("whatsapp")
        db.add(CampaignSend(occasion_id=occasion.id, user_id=user.id, channels=",".join(channels)))
        sent += 1
    occasion.sent_at = occasion.sent_at or utcnow()
    db.flush()
    return sent


@job_handler("growth.occasions")
def occasions_job(db: Session, payload: dict) -> str:
    today = (utcnow() + IST).date()
    due = (
        db.query(Occasion)
        .filter(Occasion.is_active.is_(True), Occasion.occasion_date > today, Occasion.sent_at.is_(None))
        .with_for_update(skip_locked=True)
        .all()
    )
    total = 0
    for occasion in due:
        if (occasion.occasion_date - today).days <= occasion.lead_days:
            total += run_occasion(db, occasion)
    return f"{total} nudges sent"


periodic("growth.occasions", timedelta(days=1), offset=timedelta(hours=4, minutes=30))  # 10:00 IST
