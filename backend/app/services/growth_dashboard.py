"""The weekly growth numbers for Admin → Growth (and its CSV export).

Weeks run Monday-Sunday in IST. Revenue counts shop orders that weren't
cancelled or returned, at their order total; bookings and bulk requests are
counted when made. Sources come from each order's attribution."""

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.booking import Booking
from app.models.bulk_order import BulkOrder
from app.models.growth import Referral, WalletEntry
from app.models.shop import ShopOrder
from app.models.user import User

IST = timedelta(hours=5, minutes=30)
COLUMNS = ("week_start", "new_customers", "shop_orders", "shop_revenue", "avg_order_value", "repeat_orders", "cart_recovered",
           "bookings", "bookings_completed", "bulk_requests", "referral_signups", "referral_rewards", "wallet_spent")


def _week_start(ts: datetime) -> datetime:
    local = ts + IST
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday


def weekly(db: Session, weeks: int = 8) -> list[dict]:
    this_week = _week_start(utcnow())
    starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    since = starts[0] - IST  # back to UTC
    rows = {s: {c: 0 for c in COLUMNS} | {"week_start": s.date().isoformat(), "sources": Counter()} for s in starts}

    def bucket(ts):
        return rows.get(_week_start(ts)) if ts else None

    for (created,) in db.query(User.created_at).filter(User.role == "consumer", User.created_at >= since):
        if (r := bucket(created)) is not None:
            r["new_customers"] += 1

    first_order = {}
    for consumer_id, created in db.query(ShopOrder.consumer_id, ShopOrder.created_at).filter(ShopOrder.status != "cancelled").order_by(ShopOrder.created_at):
        first_order.setdefault(consumer_id, created)
    for order in db.query(ShopOrder).filter(ShopOrder.created_at >= since, ShopOrder.status.notin_(("cancelled", "returned"))):
        if (r := bucket(order.created_at)) is None:
            continue
        r["shop_orders"] += 1
        r["shop_revenue"] += order.total_amount or 0
        r["cart_recovered"] += order.source == "abandoned_cart"
        r["repeat_orders"] += first_order.get(order.consumer_id) != order.created_at
        r["sources"][order.source or "direct"] += 1

    for created, status, source in db.query(Booking.created_at, Booking.status, Booking.source).filter(Booking.created_at >= since):
        if (r := bucket(created)) is not None:
            r["bookings"] += 1
            r["bookings_completed"] += status == "completed"
            r["sources"][source or "direct"] += 1
    for created, source in db.query(BulkOrder.created_at, BulkOrder.source).filter(BulkOrder.created_at >= since):
        if (r := bucket(created)) is not None:
            r["bulk_requests"] += 1
            r["sources"][source or "direct"] += 1

    for (created,) in db.query(Referral.created_at).filter(Referral.created_at >= since):
        if (r := bucket(created)) is not None:
            r["referral_signups"] += 1
    for credited, amount in db.query(Referral.credited_at, Referral.reward_amount).filter(Referral.credited_at >= since):
        if (r := bucket(credited)) is not None:
            r["referral_rewards"] += amount or 0
    for created, amount in db.query(WalletEntry.created_at, WalletEntry.amount).filter(
            WalletEntry.kind == "spend", WalletEntry.reversed_at.is_(None), WalletEntry.created_at >= since):
        if (r := bucket(created)) is not None:
            r["wallet_spent"] += -amount

    out = []
    for s in starts:
        r = rows[s]
        r["shop_revenue"] = round(r["shop_revenue"], 2)
        r["avg_order_value"] = round(r["shop_revenue"] / r["shop_orders"], 2) if r["shop_orders"] else 0
        r["wallet_spent"] = round(r["wallet_spent"], 2)
        r["sources"] = dict(r["sources"].most_common())
        out.append(r)
    return out
