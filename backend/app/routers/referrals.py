"""Referral codes, the wallet, attribution capture and the weekly growth
dashboard. Rules: app/services/referrals.py, attribution.py, growth_dashboard.py."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.growth import Referral, WalletEntry
from app.models.user import User
from app.services import attribution, growth_dashboard, referrals
from app.services.conversions import enabled as conversions_enabled
from app.services.platform_settings import get_platform_settings

router = APIRouter(tags=["growth"])
admin_router = APIRouter(prefix="/admin/growth", tags=["admin"], dependencies=[Depends(require_role("admin"))])
settings = get_settings()


class ReferralOut(BaseModel):
    code: str
    link: str
    friend_discount: float
    reward: float
    invited: int
    rewarded: int
    earned: float
    referred_by_code: str | None = None  # the code this user joined with


class ApplyCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class WalletEntryOut(BaseModel):
    kind: str
    amount: float
    remaining: float | None
    expires_at: datetime | None
    note: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class WalletOut(BaseModel):
    balance: float
    entries: list[WalletEntryOut]


class AttributionCaptureIn(attribution.AttributionIn):
    analytics_consent: bool | None = None


@router.get("/users/me/referral", response_model=ReferralOut)
def my_referral(user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    code = referrals.referral_code_for(db, user)
    s = get_platform_settings(db)
    mine = db.query(Referral).filter(Referral.referrer_id == user.id).all()
    joined = db.query(Referral).filter(Referral.referee_id == user.id).first()
    db.commit()
    return ReferralOut(
        code=code, link=f"{settings.public_site_url.rstrip('/')}/?ref={code}",
        friend_discount=float(s["growth_referral_friend_discount"]), reward=float(s["growth_referral_reward"]),
        invited=len(mine), rewarded=sum(r.status == "credited" for r in mine),
        earned=sum(r.reward_amount or 0 for r in mine if r.status == "credited"),
        referred_by_code=joined.code if joined else None,
    )


@router.post("/users/me/referral/apply")
def apply_referral(payload: ApplyCodeIn, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    try:
        referrals.apply_code(db, user, payload.code)
    except referrals.ReferralError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    amount = float(get_platform_settings(db)["growth_referral_friend_discount"])
    return {"status": "applied", "friend_discount": amount}


@router.get("/users/me/wallet", response_model=WalletOut)
def my_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entries = db.query(WalletEntry).filter(WalletEntry.user_id == user.id).order_by(WalletEntry.created_at.desc()).limit(100).all()
    return WalletOut(balance=referrals.balance(db, user.id), entries=entries)


@router.post("/growth/attribution")
def capture_attribution(payload: AttributionCaptureIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sent by the browser after sign-in: keeps the first touch, mirrors the
    cookie-consent choice, and applies a ?ref= code to a new customer."""
    attribution.remember_first_touch(user, payload)
    if payload.analytics_consent is not None:
        user.analytics_consent = payload.analytics_consent
    referral = None
    if payload.ref and user.role == "consumer":
        try:
            referrals.apply_code(db, user, payload.ref)
            referral = "applied"
        except referrals.ReferralError as exc:
            referral = str(exc)
    db.commit()
    return {"status": "ok", "referral": referral}


@admin_router.get("/dashboard")
def dashboard(weeks: int = Query(8, ge=1, le=52), db: Session = Depends(get_db)):
    return {"weeks": growth_dashboard.weekly(db, weeks), "totals": referrals.stats(db), "server_conversions": conversions_enabled()}


@admin_router.get("/dashboard.csv", response_class=Response)
def dashboard_csv(weeks: int = Query(12, ge=1, le=104), db: Session = Depends(get_db)):
    rows = growth_dashboard.weekly(db, weeks)
    sources = sorted({k for r in rows for k in r["sources"]})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([*growth_dashboard.COLUMNS, *[f"source:{s}" for s in sources]])
    for r in rows:
        writer.writerow([*[r[c] for c in growth_dashboard.COLUMNS], *[r["sources"].get(s, 0) for s in sources]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="aryaveda-growth-weekly.csv"'})
