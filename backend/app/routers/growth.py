"""Growth endpoints: the shopper's saved cart, marketing preferences and
one-click unsubscribe, and the admin occasion calendar."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.growth import CampaignSend, Cart, Occasion
from app.models.user import User
from app.services.growth import CartError, run_occasion, save_cart
from app.services.messaging import set_marketing_consent, verify_unsubscribe

router = APIRouter(tags=["growth"])
admin_router = APIRouter(prefix="/admin/growth", tags=["admin"], dependencies=[Depends(require_role("admin"))])


class CartIn(BaseModel):
    items: list[dict] = Field(max_length=20)


class CartOut(BaseModel):
    items: list
    updated_at: datetime | None = None


class MarketingIn(BaseModel):
    opt_in: bool


class UnsubscribeIn(BaseModel):
    u: uuid.UUID
    t: str = Field(max_length=64)


class OccasionIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    occasion_date: date
    lead_days: int = Field(default=12, ge=1, le=60)
    message: str | None = Field(default=None, max_length=300)
    is_active: bool = True


class OccasionOut(OccasionIn):
    id: uuid.UUID
    sent_at: datetime | None
    reached: int = 0

    class Config:
        from_attributes = True


@router.get("/shop/cart", response_model=CartOut)
def get_cart(user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    cart = db.get(Cart, user.id)
    return CartOut(items=cart.items if cart else [], updated_at=cart.updated_at if cart else None)


@router.put("/shop/cart", response_model=CartOut)
def put_cart(payload: CartIn, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    """The browser keeps the cart; logged-in shoppers mirror it here so it
    follows them across devices and can be recovered by a reminder."""
    try:
        cart = save_cart(db, user.id, payload.items)
    except CartError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return CartOut(items=cart.items, updated_at=cart.updated_at)


@router.put("/users/me/marketing")
def update_marketing(payload: MarketingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    set_marketing_consent(db, user, payload.opt_in, "profile")
    db.commit()
    return {"marketing_opt_in": user.marketing_opt_in}


@router.post("/marketing/unsubscribe")
def unsubscribe(payload: UnsubscribeIn, db: Session = Depends(get_db)):
    """One-click unsubscribe from the link in promotional messages - no login."""
    if not verify_unsubscribe(str(payload.u), payload.t):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This unsubscribe link isn't valid")
    user = db.get(User, payload.u)
    if user is not None:
        set_marketing_consent(db, user, False, "unsubscribe_link")
        db.commit()
    return {"status": "unsubscribed"}


def _occasion_out(db: Session, occasion: Occasion) -> OccasionOut:
    out = OccasionOut.model_validate(occasion)
    out.reached = db.query(CampaignSend).filter(CampaignSend.occasion_id == occasion.id).count()
    return out


@admin_router.get("/occasions", response_model=list[OccasionOut])
def list_occasions(db: Session = Depends(get_db)):
    return [_occasion_out(db, o) for o in db.query(Occasion).order_by(Occasion.occasion_date).all()]


@admin_router.post("/occasions", response_model=OccasionOut)
def create_occasion(payload: OccasionIn, db: Session = Depends(get_db)):
    occasion = Occasion(**payload.model_dump())
    db.add(occasion)
    db.commit()
    return _occasion_out(db, occasion)


@admin_router.put("/occasions/{occasion_id}", response_model=OccasionOut)
def update_occasion(occasion_id: uuid.UUID, payload: OccasionIn, db: Session = Depends(get_db)):
    occasion = db.get(Occasion, occasion_id)
    if occasion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Occasion not found")
    for field, value in payload.model_dump().items():
        setattr(occasion, field, value)
    db.commit()
    return _occasion_out(db, occasion)


@admin_router.post("/occasions/{occasion_id}/send-now", response_model=OccasionOut)
def send_occasion_now(occasion_id: uuid.UUID, db: Session = Depends(get_db)):
    """Sends the nudge today instead of waiting for its scheduled day (each
    customer still gets it once)."""
    occasion = db.get(Occasion, occasion_id, with_for_update=True)
    if occasion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Occasion not found")
    run_occasion(db, occasion)
    db.commit()
    return _occasion_out(db, occasion)
