"""Product reviews: verified buyers post (with up to 3 photos), anyone reads
the published ones, admins hide or restore. Rules: app/services/product_reviews.py."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.growth import ProductReview
from app.models.shop import ShopProduct
from app.models.user import User
from app.services import product_reviews as service
from app.services.product_reviews import ReviewError
from app.services.storage import save_upload

router = APIRouter(prefix="/shop/products", tags=["shop"])
admin_router = APIRouter(prefix="/admin/product-reviews", tags=["admin"], dependencies=[Depends(require_role("admin"))])

MAX_PHOTOS = 3


class ProductReviewOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    rating: int
    title: str | None
    body: str | None
    photo_urls: str | None
    status: str
    author: str | None = None  # first name only
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListOut(BaseModel):
    rating_avg: float
    rating_count: int
    breakdown: dict[int, int]  # stars -> count
    reviews: list[ProductReviewOut]


class EligibilityOut(BaseModel):
    can_review: bool
    review: ProductReviewOut | None = None


class AdminReviewOut(ProductReviewOut):
    product_name: str | None = None


class StatusIn(BaseModel):
    status: str


def _out(db: Session, review: ProductReview, cls=ProductReviewOut):
    out = cls.model_validate(review)
    user = db.get(User, review.user_id)
    out.author = ((user.name or "").split(" ")[0] or "Customer") if user else "Customer"
    return out


def _product(db: Session, product_id: uuid.UUID) -> ShopProduct:
    product = db.get(ShopProduct, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("/{product_id}/reviews", response_model=ReviewListOut)
def list_reviews(product_id: uuid.UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    product = _product(db, product_id)
    published = db.query(ProductReview).filter(ProductReview.product_id == product.id, ProductReview.status == "published")
    breakdown = {stars: 0 for stars in range(5, 0, -1)}
    for (rating,) in published.with_entities(ProductReview.rating):
        breakdown[rating] += 1
    rows = published.order_by(ProductReview.created_at.desc()).offset(offset).limit(limit).all()
    return ReviewListOut(rating_avg=product.rating_avg, rating_count=product.rating_count, breakdown=breakdown,
                         reviews=[_out(db, r) for r in rows])


@router.get("/{product_id}/reviews/mine", response_model=EligibilityOut)
def my_review(product_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    product = _product(db, product_id)
    review = db.query(ProductReview).filter(ProductReview.product_id == product.id, ProductReview.user_id == user.id).first()
    can = service.delivered_order_for(db, user.id, product.id) is not None and (review is None or review.status != "hidden")
    return EligibilityOut(can_review=can, review=_out(db, review) if review else None)


@router.post("/{product_id}/reviews", response_model=ProductReviewOut)
async def post_review(
    product_id: uuid.UUID,
    rating: int = Form(...),
    title: str | None = Form(default=None),
    body: str | None = Form(default=None),
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    product = _product(db, product_id)
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Add up to {MAX_PHOTOS} photos")
    if service.delivered_order_for(db, user.id, product.id) is None:  # before storing any photo
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can review a product once an order with it has been delivered")
    urls = []
    for photo in photos:
        try:
            urls.append(save_upload(await photo.read(), "reviews"))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Photo not accepted: {exc}")
    try:
        review = service.save_review(db, product, user.id, rating, title, body, urls)
    except ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(review)
    return _out(db, review)


@admin_router.get("", response_model=list[AdminReviewOut])
def admin_list(status_filter: str | None = Query(None, alias="status"), limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    q = db.query(ProductReview)
    if status_filter:
        q = q.filter(ProductReview.status == status_filter)
    out = []
    for review in q.order_by(ProductReview.created_at.desc()).limit(limit):
        row = _out(db, review, AdminReviewOut)
        product = db.get(ShopProduct, review.product_id)
        row.product_name = product.name if product else None
        out.append(row)
    return out


@admin_router.post("/{review_id}/status", response_model=ProductReviewOut)
def admin_set_status(review_id: uuid.UUID, payload: StatusIn, db: Session = Depends(get_db)):
    review = db.get(ProductReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    try:
        service.set_status(db, review, payload.status)
    except ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(review)
    return _out(db, review)
