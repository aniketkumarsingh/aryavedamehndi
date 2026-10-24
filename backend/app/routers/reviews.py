import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.booking import Booking
from app.models.review import Report, Review
from app.models.user import ArtistProfile, User
from app.schemas.review import ReportIn, ReportOut, ReviewIn, ReviewOut
from app.schemas.user import UserOut
from app.services.notifications import notify, notify_admins

router = APIRouter(tags=["reviews"])


def _recompute_artist_rating(db: Session, artist_id: uuid.UUID) -> None:
    reviews = (
        db.query(Review)
        .join(Booking, Booking.id == Review.booking_id)
        .filter(Booking.artist_id == artist_id, Review.by_role == "consumer")
        .all()
    )
    profile = db.get(ArtistProfile, artist_id)
    if not reviews or profile is None:
        return
    profile.rating_count = len(reviews)
    profile.rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 2)


def _recompute_consumer_rating(db: Session, consumer_id: uuid.UUID) -> None:
    reviews = (
        db.query(Review)
        .join(Booking, Booking.id == Review.booking_id)
        .filter(Booking.consumer_id == consumer_id, Review.by_role == "artist")
        .all()
    )
    consumer = db.get(User, consumer_id)
    if not reviews or consumer is None:
        return
    consumer.consumer_rating_count = len(reviews)
    consumer.consumer_rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 2)


# A report only puts the booking into dispute while the visit is live or
# awaiting payment (the Blueprint's "after arrival"). Earlier or later
# reports - a no-show, misconduct noticed after paying - still reach the
# admin queue, they just don't freeze the booking.
DISPUTABLE_STATUSES = ("arrived", "in_progress", "design_uploaded")
REPORT_CATEGORIES = ("misconduct", "no_show", "poor_quality", "safety", "other")


@router.post("/bookings/{booking_id}/review", response_model=ReviewOut)
def leave_review(
    booking_id: uuid.UUID,
    payload: ReviewIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None or user.id not in (booking.consumer_id, booking.artist_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status not in ("completed", "disputed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking isn't finished yet")

    by_role = "consumer" if user.id == booking.consumer_id else "artist"
    existing = (
        db.query(Review)
        .filter(Review.booking_id == booking_id, Review.by_role == by_role)
        .first()
    )
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You already reviewed this booking")

    review = Review(booking_id=booking_id, by_role=by_role, rating=payload.rating, comment=payload.comment)
    db.add(review)
    db.flush()
    if by_role == "consumer":
        _recompute_artist_rating(db, booking.artist_id)
    else:
        _recompute_consumer_rating(db, booking.consumer_id)

    reviewed_id = booking.artist_id if by_role == "consumer" else booking.consumer_id
    notify(db, reviewed_id, "review", "You received a review", f"{payload.rating}★ - \"{payload.comment}\"" if payload.comment else f"{payload.rating}★", f"/booking-detail/{booking_id}")

    db.commit()
    db.refresh(review)
    return review


@router.post("/bookings/{booking_id}/report", response_model=ReportOut)
def file_report(
    booking_id: uuid.UUID,
    payload: ReportIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None or user.id not in (booking.consumer_id, booking.artist_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    if payload.category not in REPORT_CATEGORIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"category must be one of {', '.join(REPORT_CATEGORIES)}")

    report = Report(booking_id=booking_id, reported_by=user.id, category=payload.category, description=payload.description)
    db.add(report)
    if booking.status in DISPUTABLE_STATUSES:
        booking.status = "disputed"

    notify_admins(db, "New report filed", f"Category: {payload.category}", f"/booking-detail/{booking_id}")

    db.commit()
    db.refresh(report)
    return report
