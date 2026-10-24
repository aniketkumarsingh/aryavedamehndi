import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.booking import Booking
from app.models.design import DesignUpload
from app.models.package import Package
from app.models.payment import Payment
from app.models.review import Report
from app.models.user import ArtistProfile, User
from app.models.shop import ShopOrder
from app.schemas.admin import (
    AdminArtistOut,
    AdminBookingOut,
    AdminDisputeOut,
    AdminOverviewOut,
    AdminUserOut,
    DisputeResolveIn,
    PlatformSettingsIn,
    PlatformSettingsOut,
)
from app.schemas.review import ReportOut, ReportResolveIn
from app.schemas.shop import ShopOrderOut, ShopOrderStatusIn
from app.schemas.user import ArtistProfileOut
from app.services.notifications import notify
from app.services.platform_settings import get_platform_settings, update_platform_settings
from app.core.time import utcnow

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.get("/overview", response_model=AdminOverviewOut)
def get_overview(db: Session = Depends(get_db)):
    total_consumers = db.query(User).filter(User.role == "consumer").count()
    total_artists = db.query(User).filter(User.role == "artist").count()
    approved_artists = db.query(ArtistProfile).filter(ArtistProfile.kyc_status == "approved").count()
    pending_kyc_count = db.query(ArtistProfile).filter(ArtistProfile.kyc_status == "pending").count()
    total_bookings = db.query(Booking).count()
    completed_bookings = db.query(Booking).filter(Booking.status == "completed").count()
    open_reports_count = db.query(Report).filter(Report.status == "open").count()
    total_platform_revenue = (
        db.query(Payment).filter(Payment.status == "paid").with_entities(Payment.platform_share, Payment.amount).all()
    )
    revenue = sum((p.platform_share if p.platform_share is not None else p.amount) for p in total_platform_revenue)

    return AdminOverviewOut(
        total_consumers=total_consumers,
        total_artists=total_artists,
        approved_artists=approved_artists,
        pending_kyc_count=pending_kyc_count,
        total_bookings=total_bookings,
        completed_bookings=completed_bookings,
        open_reports_count=open_reports_count,
        total_platform_revenue=revenue,
    )


@router.get("/bookings", response_model=list[AdminBookingOut])
def list_all_bookings(
    status_filter: str = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    flagged_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Booking, Package.name).join(Package, Package.id == Booking.package_id).order_by(Booking.created_at.desc())
    if status_filter != "all":
        query = query.filter(Booking.status == status_filter)
    if flagged_only:
        query = query.filter(Booking.arrival_flagged.is_(True))
    query = query.offset(offset).limit(limit)
    return [_admin_booking_out(db, booking, package_name) for booking, package_name in query.all()]


def _admin_booking_out(db: Session, booking: Booking, package_name: str) -> AdminBookingOut:
    consumer = db.get(User, booking.consumer_id)
    artist_user = db.get(User, booking.artist_id)
    return AdminBookingOut(
        id=booking.id,
        status=booking.status,
        package_name=package_name,
        consumer_name=consumer.name if consumer else None,
        consumer_phone=consumer.phone if consumer else "",
        artist_name=artist_user.name if artist_user else None,
        artist_phone=artist_user.phone if artist_user else "",
        scheduled_at=booking.scheduled_at,
        total_amount=booking.total_amount,
        arrival_distance_m=booking.arrival_distance_m,
        arrival_flagged=booking.arrival_flagged,
        created_at=booking.created_at,
    )


# ---------------------------------------------------------------- disputes --

@router.get("/disputes", response_model=list[AdminDisputeOut])
def list_disputes(db: Session = Depends(get_db)):
    """Disputed bookings with everything needed to rule on them: the
    reference vs. finished design side by side, the match score, and the
    reports both sides filed."""
    rows = (
        db.query(Booking, Package.name)
        .join(Package, Package.id == Booking.package_id)
        .filter(Booking.status == "disputed")
        .order_by(Booking.updated_at.desc())
        .all()
    )
    results = []
    for booking, package_name in rows:
        upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking.id).first()
        reports = db.query(Report).filter(Report.booking_id == booking.id).order_by(Report.created_at).all()
        results.append(
            AdminDisputeOut(
                booking=_admin_booking_out(db, booking, package_name),
                reference_image_url=booking.reference_design_image_url,
                completed_image_url=upload.completed_image_url if upload else None,
                similarity_score=upload.similarity_score if upload else None,
                match_status=upload.match_status if upload else None,
                advance_amount=booking.advance_amount,
                advance_status=booking.advance_status,
                reports=reports,
            )
        )
    return results


@router.post("/bookings/{booking_id}/resolve-dispute", response_model=AdminDisputeOut)
def resolve_dispute(booking_id: uuid.UUID, payload: DisputeResolveIn, db: Session = Depends(get_db)):
    from app.routers.bookings import refund_advance

    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != "disputed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking isn't disputed")

    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    link = f"/booking-detail/{booking_id}"

    if payload.outcome == "released":
        if upload is not None:
            # Admin overrides the design check, so the consumer can pay.
            upload.match_status = "consumer_confirmed"
            upload.confirmed_at = utcnow()
            booking.status = "design_uploaded"
            consumer_msg = "Our team reviewed the dispute and released the booking - you can now complete payment."
        else:
            # Disputed before a design was uploaded - let the artist finish.
            booking.status = "in_progress"
            consumer_msg = "Our team reviewed the dispute - the artist can now finish and upload the design."
        artist_msg = "Our team resolved the dispute in your favour."
    else:
        booking.status = "cancelled"
        refund_note = refund_advance(booking) if booking.advance_status == "paid" else ""
        consumer_msg = f"Our team cancelled this booking after reviewing the dispute - no platform fee is due. {refund_note}".strip()
        artist_msg = "Our team cancelled this booking after reviewing the dispute."

    booking.dispute_outcome = payload.outcome
    booking.dispute_notes = payload.notes
    booking.dispute_resolved_at = utcnow()

    for report in db.query(Report).filter(Report.booking_id == booking_id, Report.status.in_(("open", "reviewing"))).all():
        report.status = "resolved"
        report.resolution_notes = payload.notes
        report.resolved_at = utcnow()

    notify(db, booking.consumer_id, "booking", "Dispute resolved", consumer_msg, link)
    notify(db, booking.artist_id, "booking", "Dispute resolved", artist_msg, link)
    db.commit()

    package_name = db.get(Package, booking.package_id).name
    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    return AdminDisputeOut(
        booking=_admin_booking_out(db, booking, package_name),
        reference_image_url=booking.reference_design_image_url,
        completed_image_url=upload.completed_image_url if upload else None,
        similarity_score=upload.similarity_score if upload else None,
        match_status=upload.match_status if upload else None,
        advance_amount=booking.advance_amount,
        advance_status=booking.advance_status,
        reports=db.query(Report).filter(Report.booking_id == booking_id).order_by(Report.created_at).all(),
    )


# ---------------------------------------------------------------- settings --

@router.get("/settings", response_model=PlatformSettingsOut)
def get_settings_endpoint(db: Session = Depends(get_db)):
    return get_platform_settings(db)


@router.put("/settings", response_model=PlatformSettingsOut)
def update_settings_endpoint(payload: PlatformSettingsIn, db: Session = Depends(get_db)):
    """New values apply to bookings confirmed from now on - fees already
    snapshotted on confirmed bookings aren't rewritten."""
    values = update_platform_settings(db, payload.model_dump(exclude_none=True))
    db.commit()
    return values


@router.get("/users", response_model=list[AdminUserOut])
def list_all_users(
    role: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if search:
        like = f"%{search}%"
        query = query.filter((User.phone.ilike(like)) | (User.name.ilike(like)))
    return query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/users/{user_id}/suspend", response_model=AdminUserOut)
def suspend_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.role == "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't suspend an admin account")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reactivate", response_model=AdminUserOut)
def reactivate_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.get("/artists", response_model=list[AdminArtistOut])
def list_all_artists(
    status_filter: str = "all",
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Full artist directory for the admin CRM view - every artist
    regardless of KYC status, with performance stats, not just the
    pending-approval queue (see /artists/pending-kyc for that)."""
    query = db.query(ArtistProfile, User).join(User, User.id == ArtistProfile.user_id)
    if status_filter != "all":
        query = query.filter(ArtistProfile.kyc_status == status_filter)
    if search:
        like = f"%{search}%"
        query = query.filter((User.phone.ilike(like)) | (User.name.ilike(like)))
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return [_admin_artist_out(db, profile, user) for profile, user in rows]


@router.post("/artists/{artist_id}/suspend", response_model=AdminArtistOut)
def suspend_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    """Stops an artist appearing in nearby-search / taking new bookings
    (ArtistProfile.is_suspended) without locking their account entirely
    (User.is_active) - for cause (reports, quality issues) short of a full
    ban. See POST /users/{id}/suspend for the stronger, account-wide lock."""
    profile = db.get(ArtistProfile, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    profile.is_suspended = True
    notify(db, artist_id, "system", "Account suspended", "An admin has suspended your artist profile. Contact support for details.", "/artist/profile")
    db.commit()
    return _admin_artist_out(db, profile, db.get(User, artist_id))


@router.post("/artists/{artist_id}/reactivate", response_model=AdminArtistOut)
def reactivate_artist(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    profile.is_suspended = False
    notify(db, artist_id, "system", "Account reactivated", "You're visible to consumers again.", "/artist/profile")
    db.commit()
    return _admin_artist_out(db, profile, db.get(User, artist_id))


def _admin_artist_out(db: Session, profile: ArtistProfile, user: User) -> AdminArtistOut:
    completed = db.query(Booking).filter(Booking.artist_id == profile.user_id, Booking.status == "completed").all()
    return AdminArtistOut(
        user_id=profile.user_id,
        name=user.name,
        phone=user.phone,
        profile_photo_url=profile.profile_photo_url,
        kyc_status=profile.kyc_status,
        is_suspended=profile.is_suspended,
        is_active=user.is_active,
        strike_count=profile.strike_count,
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        completed_bookings=len(completed),
        total_earnings=sum(b.agreed_price or 0 for b in completed),
    )


@router.get("/artists/pending-kyc", response_model=list[ArtistProfileOut])
def list_pending_kyc(db: Session = Depends(get_db)):
    return db.query(ArtistProfile).filter(ArtistProfile.kyc_status == "pending").all()


@router.post("/artists/{artist_id}/kyc/approve", response_model=ArtistProfileOut)
def approve_kyc(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    profile.kyc_status = "approved"
    notify(db, artist_id, "kyc", "KYC approved", "You're now visible to consumers searching nearby.", "/artist/profile")
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/artists/{artist_id}/kyc/reject", response_model=ArtistProfileOut)
def reject_kyc(artist_id: uuid.UUID, db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    profile.kyc_status = "rejected"
    notify(db, artist_id, "kyc", "KYC rejected", "Please review and re-upload your documents.", "/artist/profile")
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/reports", response_model=list[ReportOut])
def list_reports(
    status_filter: str = "open",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Report)
    if status_filter != "all":
        query = query.filter(Report.status == status_filter)
    return query.order_by(Report.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/reports/{report_id}/resolve", response_model=ReportOut)
def resolve_report(report_id: uuid.UUID, payload: ReportResolveIn, db: Session = Depends(get_db)):

    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    report.status = payload.status
    report.resolution_notes = payload.resolution_notes
    report.resolved_at = utcnow()

    if payload.strike_artist:
        from app.models.booking import Booking

        booking = db.get(Booking, report.booking_id)
        if booking is not None:
            profile = db.get(ArtistProfile, booking.artist_id)
            if profile is not None:
                profile.strike_count += 1
                if profile.strike_count >= get_platform_settings(db)["strikes_before_suspension"]:
                    profile.is_suspended = True

    db.commit()
    db.refresh(report)
    return report


@router.get("/shop-orders", response_model=list[ShopOrderOut])
def list_shop_orders(
    status_filter: str = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.routers.shop import _order_out

    query = db.query(ShopOrder).order_by(ShopOrder.created_at.desc())
    if status_filter != "all":
        query = query.filter(ShopOrder.status == status_filter)
    orders = query.offset(offset).limit(limit).all()
    return [_order_out(db, o) for o in orders]


@router.post("/shop-orders/{order_id}/status", response_model=ShopOrderOut)
def update_shop_order_status(order_id: uuid.UUID, payload: ShopOrderStatusIn, db: Session = Depends(get_db)):

    from app.routers.shop import _order_out

    order = db.get(ShopOrder, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    order.status = payload.status
    if payload.status == "shipped" and order.shipped_at is None:
        order.shipped_at = utcnow()
    notify(db, order.consumer_id, "shop", "Order update", f"Your order is now '{payload.status}'.", f"/shop/orders/{order.id}")
    db.commit()
    db.refresh(order)
    return _order_out(db, order)
