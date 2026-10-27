"""Referrals and the wallet.

Referral: a new customer applies a friend's code (within REFERRAL_SIGNUP_DAYS
of joining, before their first shop order). Their first shop order gets
`growth_referral_friend_discount` off. When that order has been delivered and
its return window has passed with no return requested, the referrer gets
`growth_referral_reward` wallet credit, valid `growth_wallet_expiry_days`
(growth.referral_rewards, daily). A return request voids the reward; a
cancelled first order just frees the discount for their next order.

Wallet: credits are spent oldest-expiry first at checkout, never below a
₹1 item total. A cancelled order restores exactly the credits it used;
expired leftovers are written off daily (growth.wallet_expiry).
"""

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.growth import Referral, WalletEntry
from app.models.shop import ReturnRequest, ShopOrder
from app.models.user import User
from app.services.jobs import job_handler, periodic
from app.services.notifications import notify
from app.services.platform_settings import get_platform_settings

REFERRAL_SIGNUP_DAYS = 30
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


class ReferralError(Exception):
    pass


def money(v: float) -> float:
    return round(v + 1e-9, 2)


# --------------------------------------------------------------- referral --

def referral_code_for(db: Session, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    prefix = "".join(c for c in (user.name or "").upper() if c in CODE_ALPHABET)[:4] or "ARYA"
    for _ in range(10):
        code = prefix + "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if not db.query(User.id).filter(User.referral_code == code).first():
            user.referral_code = code
            db.flush()
            return code
    raise ReferralError("Couldn't make a referral code - please try again")


def _has_orders(db: Session, user_id) -> bool:
    return db.query(ShopOrder.id).filter(ShopOrder.consumer_id == user_id, ShopOrder.status != "cancelled").first() is not None


def apply_code(db: Session, user: User, code: str) -> Referral:
    code = (code or "").strip().upper()
    if user.referred_by or db.query(Referral).filter(Referral.referee_id == user.id).first():
        raise ReferralError("You've already used a referral code")
    referrer = db.query(User).filter(User.referral_code == code).first() if code else None
    if referrer is None or not referrer.is_active:
        raise ReferralError("This referral code isn't valid")
    if referrer.id == user.id:
        raise ReferralError("You can't use your own referral code")
    if user.role != "consumer":
        raise ReferralError("Referral codes are for customers")
    if user.created_at and utcnow() - user.created_at > timedelta(days=REFERRAL_SIGNUP_DAYS):
        raise ReferralError("Referral codes can only be used by new customers")
    if _has_orders(db, user.id):
        raise ReferralError("Referral codes apply to your first order - you've already ordered")
    if referrer.phone and user.phone and referrer.phone == user.phone:
        raise ReferralError("This referral code isn't valid")
    referral = Referral(id=uuid.uuid4(), referrer_id=referrer.id, referee_id=user.id, code=code, status="pending")
    user.referred_by = referrer.id
    db.add(referral)
    db.flush()
    return referral


def friend_discount(db: Session, user_id, items_amount: float) -> tuple[float, Referral | None]:
    """The referred friend's first-order discount, if it applies to this cart."""
    referral = db.query(Referral).filter(Referral.referee_id == user_id, Referral.status == "pending").first()
    if referral is None or _has_orders(db, user_id):
        return 0.0, None
    amount = float(get_platform_settings(db)["growth_referral_friend_discount"])
    return money(max(0.0, min(amount, items_amount - 1))), referral


def on_order_cancelled(db: Session, order: ShopOrder) -> None:
    """A cancelled first order frees the friend discount; spent wallet credit comes back."""
    restore_spend(db, order)
    referral = db.query(Referral).filter(Referral.first_order_id == order.id, Referral.status == "pending").first()
    if referral is not None:
        referral.first_order_id = None


def on_return_requested(db: Session, order: ShopOrder) -> None:
    referral = db.query(Referral).filter(Referral.first_order_id == order.id, Referral.status == "pending").first()
    if referral is not None:
        referral.status, referral.void_reason = "void", "Items from the first order were returned"


@job_handler("growth.referral_rewards")
def referral_rewards_job(db: Session, payload: dict) -> str:
    s = get_platform_settings(db)
    window = timedelta(days=int(s["shop_return_window_days"]))
    reward = float(s["growth_referral_reward"])
    due = (
        db.query(Referral).join(ShopOrder, ShopOrder.id == Referral.first_order_id)
        .filter(Referral.status == "pending", ShopOrder.status == "delivered", ShopOrder.delivered_at < utcnow() - window)
        .with_for_update(of=Referral, skip_locked=True).all()
    )
    credited = 0
    for referral in due:
        returned = db.query(ReturnRequest.id).filter(ReturnRequest.order_id == referral.first_order_id,
                                                     ReturnRequest.status != "rejected").first()
        if returned:
            referral.status, referral.void_reason = "void", "Items from the first order were returned"
            continue
        referral.status, referral.credited_at, referral.reward_amount = "credited", utcnow(), reward
        if reward > 0:
            add_credit(db, referral.referrer_id, reward, note="Referral reward", referral_id=referral.id)
            friend = db.get(User, referral.referee_id)
            notify(db, referral.referrer_id, "shop", f"₹{reward:g} referral reward",
                   f"{(friend.name or 'Your friend').split(' ')[0]} shopped with your code - ₹{reward:g} is in your wallet.", "/shop/wallet")
        credited += 1
    db.flush()
    return f"{credited} referral rewards"


periodic("growth.referral_rewards", timedelta(days=1), offset=timedelta(hours=5))


# ----------------------------------------------------------------- wallet --

def _live_credits(db: Session, user_id, lock: bool = False):
    q = (
        db.query(WalletEntry)
        .filter(WalletEntry.user_id == user_id, WalletEntry.kind == "credit", WalletEntry.remaining > 0,
                WalletEntry.expires_at > utcnow())
        .order_by(WalletEntry.expires_at, WalletEntry.created_at)
    )
    return q.with_for_update().all() if lock else q.all()


def balance(db: Session, user_id) -> float:
    return money(sum(c.remaining for c in _live_credits(db, user_id)))


def add_credit(db: Session, user_id, amount: float, note: str, referral_id=None, days: int | None = None) -> WalletEntry:
    days = days if days is not None else int(get_platform_settings(db)["growth_wallet_expiry_days"])
    entry = WalletEntry(id=uuid.uuid4(), user_id=user_id, kind="credit", amount=money(amount), remaining=money(amount),
                        expires_at=utcnow() + timedelta(days=days), referral_id=referral_id, note=note[:200])
    db.add(entry)
    return entry


def usable(db: Session, user_id, items_after_discounts: float) -> float:
    """How much wallet can go on this order (items stay at least ₹1)."""
    return money(max(0.0, min(balance(db, user_id), items_after_discounts - 1)))


def spend(db: Session, user_id, amount: float, order: ShopOrder) -> WalletEntry | None:
    if amount <= 0:
        return None
    left, allocations = money(amount), []
    for credit in _live_credits(db, user_id, lock=True):
        take = money(min(credit.remaining, left))
        credit.remaining = money(credit.remaining - take)
        allocations.append({"credit_id": str(credit.id), "amount": take})
        left = money(left - take)
        if left <= 0:
            break
    if left > 0:
        raise ReferralError("Your wallet balance changed - please review your order again")
    entry = WalletEntry(id=uuid.uuid4(), user_id=user_id, kind="spend", amount=-money(amount), order_id=order.id,
                        allocations=allocations, note=f"Order #{str(order.id)[:8].upper()}")
    db.add(entry)
    return entry


def restore_spend(db: Session, order: ShopOrder) -> None:
    for entry in db.query(WalletEntry).filter(WalletEntry.order_id == order.id, WalletEntry.kind == "spend", WalletEntry.reversed_at.is_(None)):
        for part in entry.allocations or []:
            credit = db.get(WalletEntry, uuid.UUID(part["credit_id"]))
            if credit is not None:
                credit.remaining = money((credit.remaining or 0) + part["amount"])
        entry.reversed_at = utcnow()
        db.add(WalletEntry(id=uuid.uuid4(), user_id=entry.user_id, kind="restore", amount=-entry.amount, remaining=None,
                           order_id=order.id, note=f"Order #{str(order.id)[:8].upper()} cancelled"))


@job_handler("growth.wallet_expiry")
def wallet_expiry_job(db: Session, payload: dict) -> str:
    expired = (
        db.query(WalletEntry)
        .filter(WalletEntry.kind == "credit", WalletEntry.remaining > 0, WalletEntry.expires_at <= utcnow())
        .with_for_update(skip_locked=True).all()
    )
    for credit in expired:
        db.add(WalletEntry(id=uuid.uuid4(), user_id=credit.user_id, kind="expire", amount=-credit.remaining,
                           note=f"Expired: {credit.note or 'credit'}"))
        credit.remaining = 0
    db.flush()
    return f"{len(expired)} credits expired"


periodic("growth.wallet_expiry", timedelta(days=1), offset=timedelta(hours=1))


def stats(db: Session) -> dict:
    by_status = dict(db.query(Referral.status, func.count(Referral.id)).group_by(Referral.status).all())
    outstanding = db.query(func.coalesce(func.sum(WalletEntry.remaining), 0)).filter(
        WalletEntry.kind == "credit", WalletEntry.remaining > 0, WalletEntry.expires_at > utcnow()).scalar()
    return {"referrals": by_status, "wallet_outstanding": money(float(outstanding or 0))}
