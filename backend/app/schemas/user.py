import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.services.storage import sign_media_url


class UserOut(BaseModel):
    id: uuid.UUID
    phone: str
    name: str | None
    role: str
    gender: str | None
    avatar_url: str | None
    guardian_name: str | None
    secondary_phone: str | None
    date_of_birth: date | None
    anniversary_date: date | None
    consent_given: bool
    consent_given_at: datetime | None
    marketing_opt_in: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateIn(BaseModel):
    name: str | None = None
    gender: str | None = None
    guardian_name: str | None = None
    secondary_phone: str | None = None
    date_of_birth: date | None = None
    anniversary_date: date | None = None


class AvatarPresetIn(BaseModel):
    preset_id: str  # e.g. "preset-1"


ID_PROOF_TYPES = ("aadhaar", "driving_license", "passport")


class ArtistProfileIn(BaseModel):
    # About Me
    full_name: str | None = None
    date_of_birth: date | None = None
    guardian_name: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    bio: str | None = None
    service_radius_km: float = 10
    address_text: str | None = None
    base_lat: float
    base_lng: float

    # Verification
    id_proof_type: str | None = None
    id_proof_number: str | None = None
    pan_number: str | None = None

    # Account info
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    bank_account_holder_name: str | None = None

    @field_validator("id_proof_type")
    @classmethod
    def check_id_proof_type(cls, v):
        if v is not None and v not in ID_PROOF_TYPES:
            raise ValueError(f"id_proof_type must be one of {ID_PROOF_TYPES}")
        return v

    @field_validator("bank_ifsc_code")
    @classmethod
    def check_ifsc(cls, v):
        if v:
            v = v.strip().upper()
            import re

            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", v):
                raise ValueError("bank_ifsc_code doesn't look like a valid IFSC code (e.g. HDFC0001234)")
        return v


class ConsentIn(BaseModel):
    agree: bool


class ArtistProfileOut(BaseModel):
    user_id: uuid.UUID

    # About Me
    profile_photo_url: str | None
    date_of_birth: date | None
    guardian_name: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    bio: str | None
    service_radius_km: float
    address_text: str | None
    base_lat: float | None
    base_lng: float | None

    # Verification
    kyc_status: str
    kyc_selfie_url: str | None
    id_proof_type: str | None
    id_proof_number: str | None
    id_proof_doc_url: str | None
    pan_number: str | None
    pan_doc_url: str | None
    address_proof_doc_url: str | None

    # Account info
    bank_account_number: str | None
    bank_ifsc_code: str | None
    bank_account_holder_name: str | None
    razorpay_linked_account_id: str | None

    # Consent
    consent_given: bool
    consent_given_at: datetime | None

    portfolio_urls: str | None
    rating_avg: float
    rating_count: int
    strike_count: int
    is_suspended: bool
    user: UserOut

    # Only ever returned to the artist themself and to admins - KYC docs
    # go out as short-lived signed URLs, never the bare stored path.
    @field_validator("kyc_selfie_url", "id_proof_doc_url", "pan_doc_url", "address_proof_doc_url")
    @classmethod
    def sign_private_document(cls, v):
        return sign_media_url(v)

    class Config:
        from_attributes = True


class ArtistLocationIn(BaseModel):
    label: str
    address_text: str | None = None
    lat: float
    lng: float


class ArtistLocationOut(ArtistLocationIn):
    id: uuid.UUID
    artist_id: uuid.UUID

    class Config:
        from_attributes = True


class ArtistPublicOut(BaseModel):
    """Safe-to-share artist details for a consumer who already has a
    booking with them - deliberately excludes phone (masked calling
    handles contact), bank details, and KYC documents."""

    user_id: uuid.UUID
    name: str | None
    gender: str | None
    profile_photo_url: str | None
    bio: str | None
    rating_avg: float
    rating_count: int
    portfolio_urls: str | None

    class Config:
        from_attributes = True


class ArtistDesignSummary(BaseModel):
    """An approved catalog design an artist offers, as shown on their card."""

    design_id: uuid.UUID
    name: str
    category: str | None
    price_min: float
    price_max: float
    proof_image_url: str


class ArtistNearbyOut(BaseModel):
    user_id: uuid.UUID
    designs: list[ArtistDesignSummary] = []
    name: str | None
    gender: str | None
    bio: str | None
    profile_photo_url: str | None
    rating_avg: float
    rating_count: int
    distance_km: float
    eta_minutes: int
    portfolio_urls: str | None

    class Config:
        from_attributes = True
