import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.artist_location import MAX_EXTRA_LOCATIONS, ArtistLocation
from app.models.availability import ArtistAvailability
from app.models.booking import Booking
from app.models.package import Package
from app.models.user import ArtistProfile, User
from app.schemas.availability import AvailabilityIn, AvailabilityOut
from app.schemas.dashboard import ArtistDashboardOut, SettlementModeBreakdown, TransactionOut
from app.schemas.user import (
    ArtistLocationIn,
    ArtistLocationOut,
    ArtistNearbyOut,
    ArtistProfileIn,
    ArtistProfileOut,
    ArtistPublicOut,
    ConsentIn,
)
from app.services.geo import estimate_travel_minutes, haversine_km
from app.services.razorpay_client import create_linked_account
from app.services.storage import save_upload

# Fields that carry real personal/financial data - only stored once the
# artist has given DPDP Act consent.
SENSITIVE_PROFILE_FIELDS = (
    "date_of_birth",
    "guardian_name",
    "emergency_contact_name",
    "emergency_contact_phone",
    "id_proof_type",
    "id_proof_number",
    "bank_account_number",
    "bank_ifsc_code",
    "bank_account_holder_name",
)

router = APIRouter(prefix="/artists", tags=["artists"])


@router.put("/me/profile", response_model=ArtistProfileOut)
def upsert_my_profile(
    payload: ArtistProfileIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        profile = ArtistProfile(user_id=user.id)
        db.add(profile)

    if payload.full_name is not None:
        user.name = payload.full_name

    profile.bio = payload.bio
    profile.service_radius_km = payload.service_radius_km
    profile.address_text = payload.address_text
    profile.base_lat = payload.base_lat
    profile.base_lng = payload.base_lng

    sensitive_payload = {f: getattr(payload, f) for f in SENSITIVE_PROFILE_FIELDS if getattr(payload, f) is not None}
    if sensitive_payload and not profile.consent_given:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please accept the data-consent form first (POST /artists/me/consent) before saving personal or "
            "financial details like date of birth, ID proof, or bank details.",
        )
    for field, value in sensitive_payload.items():
        setattr(profile, field, value)

    if payload.pan_number is not None:
        profile.pan_number = payload.pan_number

    db.commit()
    db.refresh(profile)
    return profile


@router.post("/me/consent", response_model=ArtistProfileOut)
def set_consent(
    payload: ConsentIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    """Records (or withdraws) DPDP Act consent for collecting and
    processing the artist's personal data - ID proof, date of birth, bank
    details, emergency contact. Required before those fields can be saved."""
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        profile = ArtistProfile(user_id=user.id)
        db.add(profile)

    profile.consent_given = payload.agree
    profile.consent_given_at = datetime.utcnow() if payload.agree else None
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/me/payout-account", response_model=ArtistProfileOut)
def set_up_payout_account(user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    """Creates a Razorpay Route linked account from the artist's bank
    details, so future bookings can be paid in full by the consumer with
    the artist's share auto-transferred (instead of the artist collecting
    the package amount directly). Safe to call again later if bank details
    change - it just creates a fresh linked account."""
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    if not profile.consent_given:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Accept the data-consent form first")
    if not (profile.bank_account_number and profile.bank_ifsc_code and profile.bank_account_holder_name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fill in your bank account details first")

    profile.razorpay_linked_account_id = create_linked_account(
        artist_name=profile.bank_account_holder_name,
        phone=user.phone,
        pan_number=profile.pan_number,
        bank={
            "account_number": profile.bank_account_number,
            "ifsc_code": profile.bank_ifsc_code,
            "account_holder_name": profile.bank_account_holder_name,
        },
    )
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/me/profile", response_model=ArtistProfileOut)
def get_my_profile(user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not set up yet")
    return profile


def _require_profile_and_consent(db: Session, user: User) -> ArtistProfile:
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    if not profile.consent_given:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please accept the data-consent form first (POST /artists/me/consent) before uploading ID documents.",
        )
    return profile


@router.post("/me/profile-photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    content = await file.read()
    profile.profile_photo_url = save_upload(content, "avatars")
    db.commit()
    return {"profile_photo_url": profile.profile_photo_url}


@router.post("/me/id-proof-doc")
async def upload_id_proof_doc(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = _require_profile_and_consent(db, user)
    if not profile.id_proof_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set id_proof_type (aadhaar/driving_license/passport) first")
    content = await file.read()
    profile.id_proof_doc_url = save_upload(content, "kyc")
    profile.kyc_status = "pending"
    db.commit()
    return {"id_proof_doc_url": profile.id_proof_doc_url, "kyc_status": profile.kyc_status}


@router.post("/me/address-proof-doc")
async def upload_address_proof_doc(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = _require_profile_and_consent(db, user)
    content = await file.read()
    profile.address_proof_doc_url = save_upload(content, "kyc")
    profile.kyc_status = "pending"
    db.commit()
    return {"address_proof_doc_url": profile.address_proof_doc_url, "kyc_status": profile.kyc_status}


@router.post("/me/kyc-selfie")
async def upload_kyc_selfie(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    content = await file.read()
    profile.kyc_selfie_url = save_upload(content, "kyc")
    db.commit()
    return {"kyc_selfie_url": profile.kyc_selfie_url}


@router.post("/me/pan-doc")
async def upload_pan_doc(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = _require_profile_and_consent(db, user)
    content = await file.read()
    profile.pan_doc_url = save_upload(content, "kyc")
    profile.kyc_status = "pending"
    db.commit()
    return {"pan_doc_url": profile.pan_doc_url, "kyc_status": profile.kyc_status}


@router.get("/me/locations", response_model=list[ArtistLocationOut])
def list_my_locations(user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    return db.query(ArtistLocation).filter(ArtistLocation.artist_id == user.id).order_by(ArtistLocation.created_at).all()


@router.post("/me/locations", response_model=ArtistLocationOut)
def add_my_location(
    payload: ArtistLocationIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    count = db.query(ArtistLocation).filter(ArtistLocation.artist_id == user.id).count()
    if count >= MAX_EXTRA_LOCATIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"You can add at most {MAX_EXTRA_LOCATIONS} extra locations (plus your primary location).",
        )
    location = ArtistLocation(artist_id=user.id, **payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.delete("/me/locations/{location_id}", status_code=204)
def remove_my_location(
    location_id: uuid.UUID,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    location = db.get(ArtistLocation, location_id)
    if location is None or location.artist_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    db.delete(location)
    db.commit()


@router.post("/me/portfolio")
async def add_portfolio_image(
    file: UploadFile = File(...),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")
    content = await file.read()
    url = save_upload(content, "portfolio")
    existing = [u for u in (profile.portfolio_urls or "").split(",") if u]
    existing.append(url)
    profile.portfolio_urls = ",".join(existing)
    db.commit()
    return {"portfolio_urls": profile.portfolio_urls}


@router.get("/nearby", response_model=list[ArtistNearbyOut])
def find_nearby_artists(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(10),
    gender: str | None = Query(None, description="Filter to a specific artist gender"),
    db: Session = Depends(get_db),
):
    candidates = (
        db.query(ArtistProfile)
        .join(User, User.id == ArtistProfile.user_id)
        .filter(
            ArtistProfile.kyc_status == "approved",
            ArtistProfile.is_suspended.is_(False),
            ArtistProfile.base_lat.isnot(None),
        )
        .all()
    )

    results: list[ArtistNearbyOut] = []
    for profile in candidates:
        if gender and profile.user.gender != gender:
            continue

        # Check the primary location plus any extra service locations, and
        # match on whichever one is closest to the consumer.
        candidate_points = [(profile.base_lat, profile.base_lng)]
        extra_locations = db.query(ArtistLocation).filter(ArtistLocation.artist_id == profile.user_id).all()
        candidate_points += [(loc.lat, loc.lng) for loc in extra_locations]

        best_lat, best_lng, distance = None, None, None
        for plat, plng in candidate_points:
            d = haversine_km(lat, lng, plat, plng)
            if distance is None or d < distance:
                distance, best_lat, best_lng = d, plat, plng

        if distance > min(radius_km, profile.service_radius_km):
            continue
        eta = estimate_travel_minutes(best_lat, best_lng, lat, lng)
        results.append(
            ArtistNearbyOut(
                user_id=profile.user_id,
                name=profile.user.name,
                gender=profile.user.gender,
                bio=profile.bio,
                profile_photo_url=profile.profile_photo_url,
                rating_avg=profile.rating_avg,
                rating_count=profile.rating_count,
                distance_km=round(distance, 1),
                eta_minutes=eta,
                portfolio_urls=profile.portfolio_urls,
            )
        )

    # Highly-rated artists first (consumers should see the best nearby
    # talent up top), distance as the tiebreaker among similarly-rated ones.
    results.sort(key=lambda r: (-r.rating_avg, -r.rating_count, r.distance_km))
    return results


@router.get("/me/dashboard", response_model=ArtistDashboardOut)
def get_my_dashboard(user: User = Depends(require_role("artist")), db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set up your profile first")

    all_bookings = db.query(Booking).filter(Booking.artist_id == user.id).all()

    orders_taken = len(all_bookings)
    orders_completed = sum(1 for b in all_bookings if b.status == "completed")
    # "Missed" = orders that didn't go through - cancelled before service, or
    # disputed after (payment withheld).
    orders_missed = sum(1 for b in all_bookings if b.status in ("cancelled", "disputed"))
    total_earnings = sum(b.agreed_price or 0 for b in all_bookings if b.status == "completed")

    breakdown: dict[str, list] = {}
    for b in all_bookings:
        if not b.settlement_mode:
            continue
        entry = breakdown.setdefault(b.settlement_mode, [0, 0.0])
        entry[0] += 1
        entry[1] += b.agreed_price or 0

    settlement_breakdown = [
        SettlementModeBreakdown(mode=mode, count=count, total_amount=total)
        for mode, (count, total) in breakdown.items()
    ]

    return ArtistDashboardOut(
        orders_taken=orders_taken,
        orders_completed=orders_completed,
        orders_missed=orders_missed,
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        total_earnings=total_earnings,
        settlement_breakdown=settlement_breakdown,
        recent_transactions=_load_transactions(db, user.id, limit=10),
    )


def _load_transactions(db: Session, artist_id: uuid.UUID, limit: int, offset: int = 0) -> list[TransactionOut]:
    rows = (
        db.query(Booking, Package.name)
        .join(Package, Package.id == Booking.package_id)
        .filter(Booking.artist_id == artist_id)
        .order_by(Booking.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        TransactionOut(
            id=b.id,
            status=b.status,
            package_name=pkg_name,
            scheduled_at=b.scheduled_at,
            agreed_price=b.agreed_price,
            platform_fee=b.platform_fee,
            settlement_mode=b.settlement_mode,
            settlement_recorded_at=b.settlement_recorded_at,
        )
        for b, pkg_name in rows
    ]


@router.get("/me/transactions", response_model=list[TransactionOut])
def list_my_transactions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    return _load_transactions(db, user.id, limit=limit, offset=offset)


@router.get("/{artist_id}/public-profile", response_model=ArtistPublicOut)
def get_public_profile(artist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(ArtistProfile, artist_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artist not found")
    return ArtistPublicOut(
        user_id=profile.user_id,
        name=profile.user.name,
        gender=profile.user.gender,
        profile_photo_url=profile.profile_photo_url,
        bio=profile.bio,
        rating_avg=profile.rating_avg,
        rating_count=profile.rating_count,
        portfolio_urls=profile.portfolio_urls,
    )


@router.get("/{artist_id}/availability", response_model=list[AvailabilityOut])
def list_availability(
    artist_id: uuid.UUID,
    from_date: date = Query(...),
    db: Session = Depends(get_db),
):
    return (
        db.query(ArtistAvailability)
        .filter(
            ArtistAvailability.artist_id == artist_id,
            ArtistAvailability.slot_date >= from_date,
            ArtistAvailability.status == "open",
        )
        .order_by(ArtistAvailability.slot_date, ArtistAvailability.start_time)
        .all()
    )


@router.post("/me/availability", response_model=AvailabilityOut)
def add_availability_slot(
    payload: AvailabilityIn,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    slot = ArtistAvailability(artist_id=user.id, **payload.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@router.delete("/me/availability/{slot_id}", status_code=204)
def remove_availability_slot(
    slot_id: uuid.UUID,
    user: User = Depends(require_role("artist")),
    db: Session = Depends(get_db),
):
    slot = db.get(ArtistAvailability, slot_id)
    if slot is None or slot.artist_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found")
    db.delete(slot)
    db.commit()
