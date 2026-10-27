"""Public pages for search: artist portfolios (/artists/<slug>) and
city/occasion landing pages (/mehndi/<slug>), plus the slug lists the
sitemap is built from. Only verified (KYC-approved), active, unsuspended
artists are ever shown."""

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Query as SAQuery, Session

from app.core.deps import require_role
from app.core.time import utcnow
from app.database import get_db
from app.models.booking import Booking
from app.models.catalog import ArtistDesign, Design
from app.models.growth import LandingPage
from app.models.review import Review
from app.models.user import ArtistProfile, User
from app.schemas.user import ArtistDesignSummary

router = APIRouter(tags=["seo"])
admin_router = APIRouter(prefix="/admin/landing-pages", tags=["admin"], dependencies=[Depends(require_role("admin"))])

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ArtistReviewOut(BaseModel):
    rating: int
    comment: str | None
    author: str | None
    created_at: datetime


class ArtistCardOut(BaseModel):
    slug: str
    name: str | None
    city: str | None
    profile_photo_url: str | None
    bio: str | None
    rating_avg: float
    rating_count: int


class ArtistPortfolioOut(ArtistCardOut):
    user_id: uuid.UUID
    portfolio_urls: list[str]
    designs: list[ArtistDesignSummary]
    reviews: list[ArtistReviewOut]
    completed_bookings: int


class DesignCardOut(BaseModel):
    id: uuid.UUID
    name: str
    image_url: str | None
    price_min: float
    price_max: float


class LandingPageIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    heading: str = Field(min_length=3, max_length=150)
    intro: str | None = Field(default=None, max_length=5000)
    city: str | None = Field(default=None, max_length=60)
    occasion: str | None = Field(default=None, max_length=30)
    meta_description: str | None = Field(default=None, max_length=300)
    is_active: bool = True


class LandingPageOut(LandingPageIn):
    slug: str
    updated_at: datetime

    class Config:
        from_attributes = True


class LandingPageViewOut(LandingPageOut):
    artists: list[ArtistCardOut]
    designs: list[DesignCardOut]


class SitemapEntry(BaseModel):
    slug: str
    updated_at: datetime | None


def listed_artists(db: Session) -> SAQuery:
    return (
        db.query(ArtistProfile).join(User, User.id == ArtistProfile.user_id)
        .filter(ArtistProfile.kyc_status == "approved", ArtistProfile.is_suspended.is_(False), User.is_active.is_(True),
                ArtistProfile.slug.isnot(None))
    )


def _card(profile: ArtistProfile) -> ArtistCardOut:
    return ArtistCardOut(slug=profile.slug, name=profile.user.name, city=profile.city, profile_photo_url=profile.profile_photo_url,
                         bio=profile.bio, rating_avg=profile.rating_avg or 0, rating_count=profile.rating_count or 0)


@router.get("/artists/by-slug/{slug}", response_model=ArtistPortfolioOut)
def artist_portfolio(slug: str, db: Session = Depends(get_db)):
    profile = listed_artists(db).filter(ArtistProfile.slug == slug).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    offers = (
        db.query(ArtistDesign).join(Design, Design.id == ArtistDesign.design_id)
        .filter(ArtistDesign.artist_id == profile.user_id, ArtistDesign.status == "approved", Design.is_active.is_(True))
        .order_by(Design.sort_order, Design.name).all()
    )
    designs = [ArtistDesignSummary(design_id=o.design_id, name=o.design.name, category=o.design.category, price_min=o.design.price_min,
                                   price_max=o.design.price_max, proof_image_url=o.proof_image_url) for o in offers]
    rows = (
        db.query(Review, User.name).join(Booking, Booking.id == Review.booking_id).join(User, User.id == Booking.consumer_id)
        .filter(Booking.artist_id == profile.user_id, Review.by_role == "consumer")
        .order_by(Review.created_at.desc()).limit(10).all()
    )
    reviews = [ArtistReviewOut(rating=r.rating, comment=r.comment, author=(name or "Customer").split(" ")[0], created_at=r.created_at)
               for r, name in rows]
    completed = db.query(func.count(Booking.id)).filter(Booking.artist_id == profile.user_id, Booking.status == "completed").scalar()
    card = _card(profile)
    return ArtistPortfolioOut(**card.model_dump(), user_id=profile.user_id,
                              portfolio_urls=[u for u in (profile.portfolio_urls or "").split(",") if u],
                              designs=designs, reviews=reviews, completed_bookings=completed or 0)


@router.get("/artists/sitemap", response_model=list[SitemapEntry])
def artist_slugs(db: Session = Depends(get_db)):
    return [SitemapEntry(slug=p.slug, updated_at=None) for p in listed_artists(db).order_by(ArtistProfile.slug)]


@router.get("/landing-pages", response_model=list[SitemapEntry])
def landing_slugs(db: Session = Depends(get_db)):
    pages = db.query(LandingPage).filter(LandingPage.is_active.is_(True)).order_by(LandingPage.slug)
    return [SitemapEntry(slug=p.slug, updated_at=p.updated_at) for p in pages]


@router.get("/landing-pages/{slug}", response_model=LandingPageViewOut)
def landing_page(slug: str, db: Session = Depends(get_db)):
    page = db.get(LandingPage, slug)
    if page is None or not page.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    artists = listed_artists(db)
    if page.city:
        artists = artists.filter(func.lower(ArtistProfile.city) == page.city.strip().lower())
    artists = artists.order_by(ArtistProfile.rating_avg.desc(), ArtistProfile.rating_count.desc()).limit(12).all()
    designs = db.query(Design).filter(Design.is_active.is_(True))
    if page.occasion:
        designs = designs.filter(Design.occasions.any(page.occasion))
    designs = designs.order_by(Design.sort_order, Design.name).limit(12).all()
    return LandingPageViewOut(
        **LandingPageOut.model_validate(page).model_dump(), artists=[_card(a) for a in artists],
        designs=[DesignCardOut(id=d.id, name=d.name, image_url=d.image_url, price_min=d.price_min, price_max=d.price_max) for d in designs],
    )


@admin_router.get("", response_model=list[LandingPageOut])
def admin_list_pages(db: Session = Depends(get_db)):
    return db.query(LandingPage).order_by(LandingPage.slug).all()


@admin_router.put("/{slug}", response_model=LandingPageOut)
def admin_save_page(slug: str, payload: LandingPageIn, db: Session = Depends(get_db)):
    if not SLUG.match(slug) or len(slug) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use lowercase letters, digits and dashes, e.g. bridal-mehndi-south-delhi")
    page = db.get(LandingPage, slug)
    if page is None:
        page = LandingPage(slug=slug, created_at=utcnow())
        db.add(page)
    for field, value in payload.model_dump().items():
        setattr(page, field, value.strip() if isinstance(value, str) else value)
    page.updated_at = utcnow()
    db.commit()
    db.refresh(page)
    return page


@admin_router.delete("/{slug}")
def admin_delete_page(slug: str, db: Session = Depends(get_db)):
    page = db.get(LandingPage, slug)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    db.delete(page)
    db.commit()
    return {"status": "deleted"}
