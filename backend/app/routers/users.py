
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.booking import Booking
from app.models.package import Package
from app.models.user import ArtistProfile, User
from app.schemas.dashboard import ConsumerDashboardOut, ConsumerRecentBookingOut, ProfileCompletionOut
from app.schemas.user import AvatarPresetIn, ConsentIn, UserOut, UserUpdateIn
from app.services.storage import save_upload
from app.core.time import utcnow

router = APIRouter(prefix="/users", tags=["users"])

PRESET_AVATAR_IDS = [f"preset-{i}" for i in range(1, 7)]

# Consumer fields that carry real personal data - only stored once the
# user has given DPDP Act consent (same pattern as the artist profile).
SENSITIVE_USER_FIELDS = ("date_of_birth", "anniversary_date", "guardian_name", "secondary_phone")


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_me(payload: UserUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field in ("name", "gender"):
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)

    sensitive_payload = {f: getattr(payload, f) for f in SENSITIVE_USER_FIELDS if getattr(payload, f) is not None}
    if sensitive_payload and not user.consent_given:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please accept the data-consent form first (POST /users/me/consent) before saving date of birth, "
            "anniversary date, guardian name or a secondary contact.",
        )
    for field, value in sensitive_payload.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.post("/me/consent", response_model=UserOut)
def set_consent(payload: ConsentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Records (or withdraws) DPDP Act consent for storing date of birth,
    anniversary date, guardian name and secondary contact number."""
    user.consent_given = payload.agree
    user.consent_given_at = utcnow() if payload.agree else None
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    user.avatar_url = save_upload(content, "avatars")
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/avatar/preset", response_model=UserOut)
def choose_preset_avatar(payload: AvatarPresetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.preset_id not in PRESET_AVATAR_IDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"preset_id must be one of {PRESET_AVATAR_IDS}")
    user.avatar_url = f"/avatars/{payload.preset_id}.svg"
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/dashboard", response_model=ConsumerDashboardOut)
def get_my_dashboard(user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    all_bookings = db.query(Booking).filter(Booking.consumer_id == user.id).all()
    total_bookings = len(all_bookings)
    completed_bookings = sum(1 for b in all_bookings if b.status == "completed")
    upcoming_bookings = sum(
        1
        for b in all_bookings
        if b.status not in ("completed", "cancelled", "disputed") and b.scheduled_at >= utcnow()
    )

    completion = ProfileCompletionOut(
        has_name=bool(user.name),
        has_gender=bool(user.gender),
        has_avatar=bool(user.avatar_url),
        percent=round(100 * (int(bool(user.name)) + int(bool(user.gender)) + int(bool(user.avatar_url))) / 3),
    )

    rows = (
        db.query(Booking, Package.name, ArtistProfile.user_id)
        .join(Package, Package.id == Booking.package_id)
        .join(ArtistProfile, ArtistProfile.user_id == Booking.artist_id)
        .filter(Booking.consumer_id == user.id)
        .order_by(Booking.created_at.desc())
        .limit(5)
        .all()
    )
    recent_bookings = []
    for b, pkg_name, artist_id in rows:
        artist_user = db.get(User, artist_id)
        recent_bookings.append(
            ConsumerRecentBookingOut(
                id=b.id,
                status=b.status,
                package_name=pkg_name,
                artist_name=artist_user.name if artist_user else None,
                scheduled_at=b.scheduled_at,
                total_amount=b.total_amount,
            )
        )

    return ConsumerDashboardOut(
        total_bookings=total_bookings,
        upcoming_bookings=upcoming_bookings,
        completed_bookings=completed_bookings,
        profile_completion=completion,
        recent_bookings=recent_bookings,
    )
