import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class BookingCreateIn(BaseModel):
    artist_id: uuid.UUID
    package_id: uuid.UUID
    address_text: str | None = None
    location_lat: float = Field(ge=-90, le=90)
    location_lng: float = Field(ge=-180, le=180)
    scheduled_at: datetime
    gender_preference: str = "same"
    reference_design_image_url: str | None = None
    # optional opening price proposal
    opening_offer: float | None = Field(default=None, gt=0, le=1_000_000)
    # If the consumer picked one of the artist's declared open slots
    # instead of a free date/time - validated server-side against the
    # artist and "open" status, then marked "booked".
    availability_slot_id: uuid.UUID | None = None

    @field_validator("reference_design_image_url")
    @classmethod
    def check_reference_image(cls, v):
        # Must be a same-origin uploaded file, never an external/absolute
        # URL - the backend fetches this server-side (to score design
        # similarity), so an arbitrary URL here would let a consumer make
        # the server issue requests to internal services (SSRF).
        # NOTE: this assumes local-disk storage (S3_BUCKET unset). If S3
        # storage is turned on, uploaded images get S3 URLs instead of
        # "/media/..." and both this check and the read-back in
        # bookings._load_reference_bytes need updating to match.
        if v is None:
            return v
        if not v.startswith("/media/") or ".." in v:
            raise ValueError("reference_design_image_url must be a path under /media/ from an upload, not an external URL")
        return v

    @field_validator("gender_preference")
    @classmethod
    def check_gender_preference(cls, v):
        if v not in ("same", "any"):
            raise ValueError("gender_preference must be 'same' or 'any'")
        return v


class BookingOut(BaseModel):
    id: uuid.UUID
    consumer_id: uuid.UUID
    artist_id: uuid.UUID
    package_id: uuid.UUID
    status: str
    address_text: str | None
    location_lat: float
    location_lng: float
    scheduled_at: datetime
    eta_minutes: float | None
    gender_preference: str
    reference_design_image_url: str | None
    agreed_price: float | None
    platform_fee: float | None
    total_amount: float | None
    settlement_mode: str | None
    settlement_recorded_at: datetime | None
    masked_call_number: str | None
    availability_slot_id: uuid.UUID | None
    advance_amount: float
    advance_status: str
    advance_paid_at: datetime | None
    artist_current_lat: float | None
    artist_current_lng: float | None
    artist_location_updated_at: datetime | None
    artist_arrived_at: datetime | None
    artist_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NegotiationOfferIn(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    message: str | None = Field(default=None, max_length=500)


class NegotiationOfferOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    proposed_by: str
    amount: float
    message: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class NegotiationRespondIn(BaseModel):
    # "accept" | "reject"
    action: str


class AdvancePaymentOrderOut(BaseModel):
    booking_id: uuid.UUID
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float
    currency: str


class AdvancePaymentVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class LocationUpdateIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
