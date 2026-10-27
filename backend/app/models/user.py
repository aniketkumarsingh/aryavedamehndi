import re
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, event, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.core.time import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=True)
    # "consumer" | "artist" | "admin"
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="consumer")
    # "female" | "male" | "other"
    gender: Mapped[str] = mapped_column(String(10), nullable=True)
    # Either an uploaded photo URL, or one of the preset mehndi-medallion
    # avatars at /avatars/preset-N.svg.
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Consumer profile details (husband's/father's name, secondary contact,
    # important dates for rebooking reminders around anniversaries etc).
    guardian_name: Mapped[str] = mapped_column(String(120), nullable=True)
    secondary_phone: Mapped[str] = mapped_column(String(15), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=True)
    anniversary_date: Mapped[date] = mapped_column(Date, nullable=True)
    # DPDP Act consent, required before date_of_birth/anniversary_date/
    # guardian_name/secondary_phone are stored - see routers/users.py.
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Promotional messages (offers, reminders) only with this; order and
    # booking updates don't need it. History in consent_records.
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_opt_in_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Traditional username/password login - only meaningful for role="admin"
    # accounts, as a convenience alternative to phone-OTP (the business
    # owner shouldn't need a registered phone number just to open the admin
    # panel). See app/core/security.py hash_password/verify_password and
    # POST /auth/admin-login. failed_login_count/locked_until are a basic
    # brute-force lockout on that endpoint.
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Two-way ratings: the average of reviews artists have left for this
    # user as a consumer, shown to artists before they accept a request.
    consumer_rating_avg: Mapped[float] = mapped_column(Float, default=0)
    consumer_rating_count: Mapped[int] = mapped_column(Integer, default=0)

    artist_profile: Mapped["ArtistProfile"] = relationship(back_populates="user", uselist=False)


class ArtistProfile(Base):
    __tablename__ = "artist_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    # ---- About Me ----------------------------------------------------
    profile_photo_url: Mapped[str] = mapped_column(String(500), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=True)
    guardian_name: Mapped[str] = mapped_column(String(120), nullable=True)  # father's or husband's name
    emergency_contact_name: Mapped[str] = mapped_column(String(120), nullable=True)
    emergency_contact_phone: Mapped[str] = mapped_column(String(15), nullable=True)
    bio: Mapped[str] = mapped_column(Text, nullable=True)
    service_radius_km: Mapped[float] = mapped_column(Float, default=10)
    # Permanent/primary address - human-readable text, alongside the
    # coordinates used for distance search. Up to 2 more addresses live in
    # ArtistLocation.
    address_text: Mapped[str] = mapped_column(Text, nullable=True)
    base_lat: Mapped[float] = mapped_column(Float, nullable=True)
    base_lng: Mapped[float] = mapped_column(Float, nullable=True)

    # ---- Verification --------------------------------------------------
    # "pending" | "approved" | "rejected" - the overall admin approval gate
    kyc_status: Mapped[str] = mapped_column(String(20), default="pending")
    kyc_selfie_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # "aadhaar" | "driving_license" | "passport"
    id_proof_type: Mapped[str] = mapped_column(String(20), nullable=True)
    id_proof_number: Mapped[str] = mapped_column(String(30), nullable=True)
    id_proof_doc_url: Mapped[str] = mapped_column(String(500), nullable=True)
    pan_number: Mapped[str] = mapped_column(String(15), nullable=True)
    pan_doc_url: Mapped[str] = mapped_column(String(500), nullable=True)
    address_proof_doc_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # ---- Account info -----------------------------------------------------
    # Used both for artist reference, and (once razorpay_linked_account_id
    # is set) as the payout destination for Razorpay Route split payments -
    # see app/services/razorpay_client.py. Until an artist has a linked
    # account, payment still falls back to the old direct-settlement flow
    # (platform only collects its fee; the package amount is paid to the
    # artist outside the app and recorded via Booking.settlement_mode).
    bank_account_number: Mapped[str] = mapped_column(String(30), nullable=True)
    bank_ifsc_code: Mapped[str] = mapped_column(String(11), nullable=True)
    bank_account_holder_name: Mapped[str] = mapped_column(String(120), nullable=True)
    razorpay_linked_account_id: Mapped[str] = mapped_column(String(60), nullable=True)

    # ---- DPDP Act consent -----------------------------------------------
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    portfolio_urls: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated for simplicity
    # Public portfolio page /artists/<slug>, and the city for local pages.
    slug: Mapped[str] = mapped_column(String(90), nullable=True, unique=True)
    city: Mapped[str] = mapped_column(String(60), nullable=True)
    rating_avg: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    strike_count: Mapped[int] = mapped_column(Integer, default=0)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="artist_profile")


@event.listens_for(ArtistProfile, "before_insert")
def _give_artist_a_slug(mapper, connection, target):
    """Every artist gets a stable public address, /artists/<name>-<id6>."""
    if not target.slug:
        name = connection.execute(select(User.name).where(User.id == target.user_id)).scalar() or "artist"
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "artist"
        target.slug = f"{base}-{str(target.user_id)[:6]}"
