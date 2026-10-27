"""Verified product reviews.

Only a customer with a delivered order containing the product can review it;
one review per customer per product (posting again edits it). Reviews go
live straight away; admins can hide abusive or off-topic ones. The product's
rating_avg/rating_count always reflect the published reviews.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.growth import ProductReview
from app.models.shop import ShopOrder, ShopOrderItem, ShopProduct
from app.services.notifications import notify_admins


class ReviewError(Exception):
    pass


def delivered_order_for(db: Session, user_id, product_id) -> ShopOrder | None:
    """The customer's most recent delivered order that contains the product."""
    return (
        db.query(ShopOrder).join(ShopOrderItem, ShopOrderItem.order_id == ShopOrder.id)
        .filter(ShopOrder.consumer_id == user_id, ShopOrder.status == "delivered", ShopOrderItem.product_id == product_id)
        .order_by(ShopOrder.delivered_at.desc().nullslast()).first()
    )


def recompute_rating(db: Session, product: ShopProduct) -> None:
    db.flush()
    avg, count = (
        db.query(func.avg(ProductReview.rating), func.count(ProductReview.id))
        .filter(ProductReview.product_id == product.id, ProductReview.status == "published").one()
    )
    product.rating_avg, product.rating_count = round(float(avg or 0), 2), int(count or 0)


def save_review(db: Session, product: ShopProduct, user_id, rating: int, title: str | None, body: str | None,
                photo_urls: list[str]) -> ProductReview:
    if not 1 <= rating <= 5:
        raise ReviewError("Pick a rating from 1 to 5 stars")
    order = delivered_order_for(db, user_id, product.id)
    if order is None:
        raise ReviewError("You can review a product once an order with it has been delivered")
    review = db.query(ProductReview).filter(ProductReview.product_id == product.id, ProductReview.user_id == user_id).first()
    if review is None:
        review = ProductReview(product_id=product.id, user_id=user_id, order_id=order.id)
        db.add(review)
    elif review.status == "hidden":
        raise ReviewError("This review was removed by our team and can't be edited")
    review.rating = rating
    review.title = (title or "").strip()[:120] or None
    review.body = (body or "").strip()[:3000] or None
    if photo_urls:
        review.photo_urls = ",".join(photo_urls)
    review.status = "published"
    recompute_rating(db, product)
    if rating <= 2:
        notify_admins(db, "Low product review", f"{rating}★ on {product.name}: {(review.body or review.title or '')[:120]}", "/admin")
    return review


def set_status(db: Session, review: ProductReview, status: str) -> None:
    if status not in ("published", "hidden"):
        raise ReviewError("Status must be published or hidden")
    review.status = status
    recompute_rating(db, db.get(ShopProduct, review.product_id))
