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
from app.services.notifications import notify

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

    report = Report(booking_id=booking_id, reported_by=user.id, category=payload.category, description=payload.description)
    db.add(report)
    booking.status = "disputed"

    for admin in db.query(User).filter(User.role == "admin").all():
        notify(db, admin.id, "system", "New report filed", f"Category: {payload.category}", f"/booking-detail/{booking_id}")

    db.commit()
    db.refresh(report)
    return report
