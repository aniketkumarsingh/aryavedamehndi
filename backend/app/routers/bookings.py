import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.availability import ArtistAvailability
from app.models.booking import Booking, NegotiationOffer
from app.models.catalog import ArtistDesign, Design
from app.models.design import DesignUpload
from app.models.package import Package
from app.models.user import ArtistProfile, User
from app.schemas.booking import (
    AdvancePaymentOrderOut,
    ReferenceImageOut,
    AdvancePaymentVerifyIn,
    BookingCreateIn,
    BookingOut,
    LocationUpdateIn,
    NegotiationOfferIn,
    NegotiationOfferOut,
    NegotiationRespondIn,
)
from app.schemas.dashboard import SettlementIn
from app.services import attribution
from app.schemas.design import ConsumerConfirmIn, DesignUploadOut
from app.services.geo import estimate_travel_minutes, haversine_km
from app.services.platform_settings import get_platform_settings
from app.services.pricing import check_price_in_band, compute_platform_fee
from app.services.similarity import score_similarity
from app.services.notifications import notify, notify_admins
from app.services.razorpay_client import create_order, verify_payment_signature
from app.services.messaging import set_marketing_consent, whatsapp_user
from app.services.refunds import issue_refund
from app.services.storage import save_upload
from app.services.telephony import provision_masked_number
from app.core.time import utcnow

router = APIRouter(prefix="/bookings", tags=["bookings"])
settings = get_settings()


def _provision_call_masking(db: Session, booking: Booking) -> None:
    consumer = db.get(User, booking.consumer_id)
    artist_user = db.get(User, booking.artist_id)
    if consumer is None or artist_user is None:
        return
    masked_number, provider_ref = provision_masked_number(booking.id, consumer.phone, artist_user.phone)
    booking.masked_call_number = masked_number
    booking.masked_call_provider_ref = provider_ref


def _bookable_design(db: Session, design_id: uuid.UUID, package: Package, artist_id: uuid.UUID) -> Design:
    design = db.get(Design, design_id)
    if design is None or not design.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
    if design.package_id != package.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That design belongs to a different package")
    offered = (
        db.query(ArtistDesign)
        .filter(ArtistDesign.artist_id == artist_id, ArtistDesign.design_id == design.id, ArtistDesign.status == "approved")
        .first()
    )
    if offered is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This artist doesn't offer that design")
    return design


def _check_negotiable(package: Package) -> None:
    if not package.negotiable:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This package has a fixed price range and can't be negotiated")


def _confirm_booking_at_price(db: Session, booking: Booking, agreed_price: float) -> None:
    """Shared by both acceptance paths: an artist accepting the consumer's
    (or their own) pending offer, and an artist directly accepting a plain
    request that never had an offer attached (see POST /{id}/accept)."""
    check_price_in_band(booking.package, agreed_price, booking.design)
    booking.agreed_price = agreed_price
    booking.platform_fee = compute_platform_fee(db, agreed_price)
    booking.total_amount = booking.agreed_price + booking.platform_fee
    booking.status = "confirmed"
    artist = db.get(User, booking.artist_id)
    whatsapp_user(db, booking.consumer_id, "booking_confirmed", artist=(artist.name if artist else None) or "your artist",
                  when=f"{booking.scheduled_at + timedelta(hours=5, minutes=30):%d %b, %I:%M %p}")
    db.query(NegotiationOffer).filter(
        NegotiationOffer.booking_id == booking.id, NegotiationOffer.status == "pending"
    ).update({"status": "rejected"})
    _provision_call_masking(db, booking)


def mark_advance_paid(db: Session, booking: Booking, payment_id: str, signature: str | None = None) -> bool:
    """Records the advance as paid - from the customer's browser or the
    Razorpay webhook, whichever arrives first. Returns False if it was
    already recorded. Doesn't commit."""
    if booking.advance_status == "paid":
        return False
    booking.advance_razorpay_payment_id = payment_id
    booking.advance_razorpay_signature = signature
    booking.advance_status = "paid"
    booking.advance_paid_at = utcnow()
    notify(
        db,
        booking.artist_id,
        "booking",
        "Advance paid - slot secured",
        f"₹{booking.advance_amount} advance received. You're clear to head out once it's time.",
        f"/booking-detail/{booking.id}",
    )
    return True


def refund_advance(db: Session, booking: Booking, initiated_by=None) -> str:
    """Refunds a paid advance (queued and tracked - see app/services/refunds)
    and returns a consumer-facing note. Shared by early cancellation and an
    admin cancelling a disputed booking."""
    issue_refund(db, target_type="booking_advance", target_id=booking.id, payment_id=booking.advance_razorpay_payment_id,
                 reason="Booking cancelled before the artist set out", initiated_by=initiated_by)
    booking.advance_status = "refund_pending"  # "refunded" once Razorpay confirms
    return f"Your ₹{booking.advance_amount} advance is being refunded - banks usually show it within 5-7 working days."


def _get_booking_or_404(db: Session, booking_id: uuid.UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


def _ensure_party(booking: Booking, user: User) -> None:
    if user.role == "admin":
        return
    if user.id not in (booking.consumer_id, booking.artist_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not part of this booking")


# ---------------------------------------------------------------- create --

@router.post("", response_model=BookingOut)
def create_booking(
    payload: BookingCreateIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    package = db.get(Package, payload.package_id)
    if package is None or not package.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")

    artist_profile = db.get(ArtistProfile, payload.artist_id)
    if artist_profile is None or artist_profile.kyc_status != "approved" or artist_profile.is_suspended:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Artist is not currently bookable")

    if payload.gender_preference == "same" and user.gender and artist_profile.user.gender != user.gender:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Artist gender doesn't match your safety preference. Pass gender_preference='any' to override.",
        )

    design = None
    reference_image_url = payload.reference_design_image_url
    if payload.design_id is not None:
        design = _bookable_design(db, payload.design_id, package, payload.artist_id)
        # The catalog photo is what the finished work is verified against. An
        # illustration isn't a fair reference, so the consumer confirms instead.
        reference_image_url = design.image_url if design.image_kind == "photo" else None

    if payload.opening_offer is not None:
        _check_negotiable(package)
        check_price_in_band(package, payload.opening_offer, design)

    eta = estimate_travel_minutes(
        artist_profile.base_lat, artist_profile.base_lng, payload.location_lat, payload.location_lng
    )

    slot = None
    if payload.availability_slot_id is not None:
        slot = db.get(ArtistAvailability, payload.availability_slot_id)
        if slot is None or slot.artist_id != payload.artist_id or slot.status != "open":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That time slot is no longer available - please pick another.")

    booking = Booking(
        consumer_id=user.id,
        artist_id=payload.artist_id,
        package_id=payload.package_id,
        address_text=payload.address_text,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        scheduled_at=payload.scheduled_at,
        gender_preference=payload.gender_preference,
        reference_design_image_url=reference_image_url,
        design_id=design.id if design else None,
        eta_minutes=eta,
        status="requested",
        availability_slot_id=slot.id if slot else None,
        advance_amount=package.advance_amount,
        advance_status="pending" if package.advance_amount > 0 else "not_required",
    )
    db.add(booking)
    db.flush()

    if slot is not None:
        slot.status = "booked"

    if payload.opening_offer is not None:
        booking.status = "negotiating"
        db.add(NegotiationOffer(booking_id=booking.id, proposed_by="consumer", amount=payload.opening_offer))

    notify(
        db,
        payload.artist_id,
        "booking",
        "New booking request",
        f"{user.name or 'A consumer'} wants to book you for {package.name}.",
        f"/booking-detail/{booking.id}",
    )

    if payload.marketing_opt_in:
        set_marketing_consent(db, user, True, "booking")
    booking.attribution = attribution.clean(payload.attribution)
    booking.source = attribution.source_of(booking.attribution or user.attribution)
    attribution.remember_first_touch(user, payload.attribution)
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/reference-image", response_model=ReferenceImageOut)
async def upload_reference_image(file: UploadFile = File(...), user: User = Depends(require_role("consumer"))):
    """A consumer's own design to book (or to add to a bulk order). Priced at
    its package's range like any non-catalog booking, and it becomes the
    reference the finished work is scored against."""
    return ReferenceImageOut(url=save_upload(await file.read(), "references"))


@router.get("", response_model=list[BookingOut])
def list_my_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "artist":
        return db.query(Booking).filter(Booking.artist_id == user.id).order_by(Booking.created_at.desc()).all()
    return db.query(Booking).filter(Booking.consumer_id == user.id).order_by(Booking.created_at.desc()).all()


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    return booking


# ----------------------------------------------------------- negotiation --

@router.post("/{booking_id}/offers", response_model=NegotiationOfferOut)
def make_offer(
    booking_id: uuid.UUID,
    payload: NegotiationOfferIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    if booking.status not in ("requested", "negotiating"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking is no longer negotiable")
    package = db.get(Package, booking.package_id)
    _check_negotiable(package)
    check_price_in_band(package, payload.amount, booking.design)

    proposed_by = "consumer" if user.id == booking.consumer_id else "artist"
    offer = NegotiationOffer(booking_id=booking.id, proposed_by=proposed_by, amount=payload.amount, message=payload.message)
    db.add(offer)
    booking.status = "negotiating"

    other_party_id = booking.artist_id if proposed_by == "consumer" else booking.consumer_id
    notify(db, other_party_id, "booking", "New price offer", f"₹{payload.amount} proposed for your booking.", f"/booking-detail/{booking_id}")

    db.commit()
    db.refresh(offer)
    return offer


@router.get("/{booking_id}/offers", response_model=list[NegotiationOfferOut])
def list_offers(booking_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    return (
        db.query(NegotiationOffer)
        .filter(NegotiationOffer.booking_id == booking_id)
        .order_by(NegotiationOffer.created_at)
        .all()
    )


@router.post("/{booking_id}/offers/{offer_id}/respond", response_model=BookingOut)
def respond_to_offer(
    booking_id: uuid.UUID,
    offer_id: uuid.UUID,
    payload: NegotiationRespondIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    offer = db.get(NegotiationOffer, offer_id)
    if offer is None or offer.booking_id != booking_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")

    responder_role = "consumer" if user.id == booking.consumer_id else "artist"
    if offer.proposed_by == responder_role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't respond to your own offer")

    proposer_id = booking.consumer_id if offer.proposed_by == "consumer" else booking.artist_id

    if payload.action == "accept":
        offer.status = "accepted"
        _confirm_booking_at_price(db, booking, offer.amount)
        notify(db, proposer_id, "booking", "Offer accepted", f"Your ₹{offer.amount} offer was accepted - booking confirmed!", f"/booking-detail/{booking_id}")
    elif payload.action == "reject":
        offer.status = "rejected"
        notify(db, proposer_id, "booking", "Offer declined", f"Your ₹{offer.amount} offer was declined.", f"/booking-detail/{booking_id}")
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action must be 'accept' or 'reject'")

    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/accept", response_model=BookingOut)
def accept_booking_directly(
    booking_id: uuid.UUID,
    payload: NegotiationOfferIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """Lets the artist confirm a booking outright at a price they name,
    without the offer/counter-offer dance - for the common case where the
    consumer just requested the package's listed price and the artist is
    simply fine with it. (The negotiation endpoints above still exist for
    when either side wants to propose something different first.)"""
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status not in ("requested", "negotiating"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking is no longer negotiable")

    _confirm_booking_at_price(db, booking, payload.amount)
    notify(
        db,
        booking.consumer_id,
        "booking",
        "Booking confirmed",
        f"Your artist accepted at ₹{payload.amount} - booking confirmed!",
        f"/booking-detail/{booking_id}",
    )
    db.commit()
    db.refresh(booking)
    return booking


# --------------------------------------------------- advance/deposit pay --

@router.post("/{booking_id}/advance/order", response_model=AdvancePaymentOrderOut)
def create_advance_order(booking_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    if booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.advance_status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No advance payment is due on this booking")

    order = create_order(booking.advance_amount, receipt=f"advance_{booking.id}")
    booking.advance_razorpay_order_id = order["id"]
    db.commit()

    return AdvancePaymentOrderOut(
        booking_id=booking.id,
        razorpay_order_id=order["id"],
        razorpay_key_id=settings.razorpay_key_id or "dev_mode_no_key",
        amount=booking.advance_amount,
        currency="INR",
    )


@router.post("/{booking_id}/advance/verify", response_model=BookingOut)
def verify_advance_payment(
    booking_id: uuid.UUID,
    payload: AdvancePaymentVerifyIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    booking = _get_booking_or_404(db, booking_id)
    db.refresh(booking, with_for_update=True)  # one settle at a time (see the webhook)
    if booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.advance_razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching advance payment order")

    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    mark_advance_paid(db, booking, payload.razorpay_payment_id, payload.razorpay_signature)
    db.commit()
    db.refresh(booking)
    return booking


# ------------------------------------------------------- status updates --

@router.post("/{booking_id}/enroute", response_model=BookingOut)
def mark_enroute(booking_id: uuid.UUID, user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status != "confirmed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking must be confirmed first")
    if booking.advance_status == "pending":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The consumer hasn't paid the ₹{booking.advance_amount} advance yet - wait for that before heading out.",
        )
    booking.status = "artist_enroute"
    notify(db, booking.consumer_id, "booking", "Your artist is on the way", None, f"/booking-detail/{booking_id}")
    whatsapp_user(db, booking.consumer_id, "artist_en_route", artist=user.name or "Your artist")
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/location", response_model=BookingOut)
def update_live_location(
    booking_id: uuid.UUID,
    payload: LocationUpdateIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """Called periodically by the artist's browser while en route, so the
    consumer can see a live "how far away is my artist" view - Uber-style.
    Only meaningful (and only accepted) while status is artist_enroute;
    once they've arrived, artist_arrived_lat/lng is the record that matters."""
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status != "artist_enroute":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Live location is only tracked while you're marked en route")

    booking.artist_current_lat = payload.lat
    booking.artist_current_lng = payload.lng
    booking.artist_location_updated_at = utcnow()
    booking.eta_minutes = estimate_travel_minutes(payload.lat, payload.lng, booking.location_lat, booking.location_lng)
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/arrived", response_model=BookingOut)
def mark_arrived(
    booking_id: uuid.UUID,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status != "artist_enroute":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mark yourself en route before checking in")
    booking.status = "arrived"
    booking.artist_arrived_at = utcnow()
    booking.artist_arrived_lat = lat
    booking.artist_arrived_lng = lng

    # Geo check-in audit - a check-in far from the booking address doesn't
    # block the artist (GPS can be off indoors), it's flagged for ops.
    distance_m = round(haversine_km(lat, lng, booking.location_lat, booking.location_lng) * 1000)
    booking.arrival_distance_m = distance_m
    threshold_m = get_platform_settings(db)["checkin_flag_distance_m"]
    if distance_m > threshold_m:
        booking.arrival_flagged = True
        notify_admins(
            db,
            "Check-in far from booking address",
            f"Artist checked in {distance_m / 1000:.1f} km from the booking address (limit {threshold_m} m).",
            f"/booking-detail/{booking_id}",
        )

    notify(db, booking.consumer_id, "booking", "Your artist has arrived", None, f"/booking-detail/{booking_id}")
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/start", response_model=BookingOut)
def mark_in_progress(booking_id: uuid.UUID, user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status != "arrived":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Check in as arrived before starting the mehndi")
    booking.status = "in_progress"
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    if booking.status == "cancelled":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Booking is already cancelled")
    if booking.status == "disputed":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This booking is under dispute review - our team will resolve it")
    if booking.status in ("in_progress", "design_uploaded", "completed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too late to cancel - raise a report instead")

    # Advance-deposit cancellation policy: refundable while the artist
    # hasn't left yet (requested/negotiating/confirmed); forfeited once
    # they're already traveling or on-site (artist_enroute/arrived) -
    # that's the whole point of the deposit, to cover the artist's wasted
    # trip. See Package.advance_amount.
    advance_note = None
    if booking.advance_status == "paid":
        if booking.status in ("artist_enroute", "arrived"):
            booking.advance_status = "forfeited"
            advance_note = f" The ₹{booking.advance_amount} advance is forfeited since the artist had already headed out."
        else:
            advance_note = " " + refund_advance(db, booking, initiated_by=user.id)

    if booking.availability_slot_id is not None and booking.advance_status != "forfeited":
        slot = db.get(ArtistAvailability, booking.availability_slot_id)
        if slot is not None and slot.status == "booked":
            slot.status = "open"

    booking.status = "cancelled"
    other_party_id = booking.artist_id if user.id == booking.consumer_id else booking.consumer_id
    notify(db, other_party_id, "booking", "Booking cancelled", advance_note, f"/booking-detail/{booking_id}")
    if advance_note:
        notify(db, user.id, "booking", "Booking cancelled", advance_note.strip(), f"/booking-detail/{booking_id}")
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{booking_id}/settlement", response_model=BookingOut)
def record_settlement(
    booking_id: uuid.UUID,
    payload: SettlementIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """The artist records how they were paid the package amount directly
    by the consumer (UPI, cash, etc). This is separate from the platform
    fee, which is always collected through Razorpay - see payments.py."""
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if payload.mode not in ("upi", "cash", "bank_transfer", "other"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode must be upi, cash, bank_transfer or other")
    if booking.status not in ("design_uploaded", "completed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete the service before recording settlement")

    booking.settlement_mode = payload.mode
    booking.settlement_recorded_at = utcnow()
    db.commit()
    db.refresh(booking)
    return booking


# ------------------------------------------------------------ design gate --

@router.post("/{booking_id}/design-upload", response_model=DesignUploadOut)
async def upload_design(
    booking_id: uuid.UUID,
    file: UploadFile = File(...),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """Uploading the finished design is also the artist's check-out - the
    optional lat/lng is logged alongside the arrival check-in."""
    booking = _get_booking_or_404(db, booking_id)
    if booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    if booking.status not in ("arrived", "in_progress"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mark the booking in progress before uploading the design")

    content = await file.read()
    completed_url = save_upload(content, "designs")

    score = None
    match_status = "needs_consumer_confirmation"
    if booking.reference_design_image_url:
        try:
            ref_bytes = _load_reference_bytes(booking.reference_design_image_url)
            score = score_similarity(content, ref_bytes)
            if score >= get_platform_settings(db)["design_match_threshold"]:
                match_status = "auto_matched"
        except Exception:
            score = None  # reference unreadable - fall back to manual confirmation

    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    if upload is None:
        upload = DesignUpload(booking_id=booking_id)
        db.add(upload)
    upload.completed_image_url = completed_url
    upload.reference_image_url = booking.reference_design_image_url
    upload.similarity_score = score
    upload.match_status = match_status

    booking.status = "design_uploaded"
    booking.artist_completed_at = utcnow()
    if lat is not None and lng is not None:
        booking.artist_completed_lat = lat
        booking.artist_completed_lng = lng
    notify(
        db,
        booking.consumer_id,
        "booking",
        "Your mehndi design is ready",
        "Please confirm the design so payment can be released.",
        f"/booking-detail/{booking_id}",
    )
    db.commit()
    db.refresh(upload)
    return upload


def _load_reference_bytes(url: str) -> bytes:
    """Reads a previously-uploaded reference image from local disk.

    Deliberately does not fetch arbitrary/external URLs: `url` is
    user-supplied (the consumer's chosen reference design) and the schema
    validator on BookingCreateIn already restricts it to "/media/..." -
    fetching arbitrary URLs server-side here would be an SSRF vector.
    """
    from app.services.storage import MEDIA_DIR

    if not url.startswith("/media/"):
        raise ValueError("reference image must be a local /media/ upload")

    candidate = (MEDIA_DIR / url.removeprefix("/media/")).resolve()
    media_root = MEDIA_DIR.resolve()
    if media_root not in candidate.parents and candidate != media_root:
        raise ValueError("reference image path escapes the media directory")

    return candidate.read_bytes()


@router.post("/{booking_id}/design-confirm", response_model=DesignUploadOut)
def confirm_design(
    booking_id: uuid.UUID,
    payload: ConsumerConfirmIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    booking = _get_booking_or_404(db, booking_id)
    if booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your booking")
    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No design uploaded yet")
    if booking.status != "design_uploaded" or upload.match_status != "needs_consumer_confirmation":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This design doesn't need your confirmation")

    if payload.satisfied:
        upload.match_status = "consumer_confirmed"
        upload.confirmed_at = utcnow()
        notify(db, booking.artist_id, "booking", "Design confirmed", "The consumer is happy with the design.", f"/booking-detail/{booking_id}")
    else:
        upload.match_status = "disputed"
        booking.status = "disputed"
        notify(db, booking.artist_id, "booking", "Design disputed", "The consumer wasn't satisfied - check the booking.", f"/booking-detail/{booking_id}")

    db.commit()
    db.refresh(upload)
    return upload


@router.get("/{booking_id}/design", response_model=DesignUploadOut)
def get_design(booking_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = _get_booking_or_404(db, booking_id)
    _ensure_party(booking, user)
    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No design uploaded yet")
    return upload
