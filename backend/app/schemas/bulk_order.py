import uuid
from datetime import datetime, timezone
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

from app.schemas.booking import check_reference_image_url
from app.schemas.catalog import DesignOccasion

# Events people book mehndi for in bulk that aren't design occasions in
# the catalog. Labels: frontend/src/lib/pricing.js BULK_OCCASIONS.
BulkOnlyOccasion = Literal["mehndi-ceremony", "corporate", "society-event", "other"]
BULK_OCCASIONS = set(get_args(BulkOnlyOccasion)) | set(get_args(DesignOccasion))

MAX_LINES = 20
MAX_PEOPLE_PER_LINE = 500


class OrderLineIn(BaseModel):
    package_id: uuid.UUID
    # Optional catalog design - its own band replaces the package's.
    design_id: uuid.UUID | None = None
    quantity: int = Field(ge=1, le=MAX_PEOPLE_PER_LINE)


class EstimateIn(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1, max_length=MAX_LINES)


class EstimateLineOut(BaseModel):
    package_id: uuid.UUID
    design_id: uuid.UUID | None
    quantity: int
    unit_price_min: float
    unit_price_max: float
    unit_advance: float


class EstimateOut(BaseModel):
    """See app/services/pricing.py order_estimate."""

    lines: list[EstimateLineOut]
    people: int
    subtotal_min: float
    subtotal_max: float
    platform_fee_min: float
    platform_fee_max: float
    total_min: float
    total_max: float
    advance_amount: float


class PricingPolicyOut(BaseModel):
    platform_fee_mode: str
    platform_fee_percent: float
    platform_fee_flat: float


class BulkOrderLineIn(OrderLineIn):
    # The consumer's own design for this group (POST /bookings/reference-image).
    reference_image_url: str | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("reference_image_url")
    @classmethod
    def check_reference_image(cls, v):
        return check_reference_image_url(v)


class BulkOrderCreateIn(BaseModel):
    occasion: str
    event_at: datetime
    address_text: str = Field(min_length=5, max_length=500)
    location_lat: float | None = Field(default=None, ge=-90, le=90)
    location_lng: float | None = Field(default=None, ge=-180, le=180)
    gender_preference: str = "same"
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[BulkOrderLineIn] = Field(min_length=1, max_length=MAX_LINES)

    @field_validator("event_at")
    @classmethod
    def to_naive_utc(cls, v: datetime):
        # Every DateTime column stores naive UTC (app/core/time.py).
        return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v

    @field_validator("occasion")
    @classmethod
    def check_occasion(cls, v):
        if v not in BULK_OCCASIONS:
            raise ValueError("Unknown occasion")
        return v

    @field_validator("gender_preference")
    @classmethod
    def check_gender_preference(cls, v):
        if v not in ("same", "any"):
            raise ValueError("gender_preference must be 'same' or 'any'")
        return v


class QuoteLineIn(BaseModel):
    line_id: uuid.UUID
    unit_price: float = Field(gt=0, le=1_000_000)


class BulkOrderQuoteIn(BaseModel):
    lines: list[QuoteLineIn] = Field(min_length=1, max_length=MAX_LINES)
    admin_note: str | None = Field(default=None, max_length=2000)


class BulkOrderCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BulkOrderLineOut(BaseModel):
    id: uuid.UUID
    package_id: uuid.UUID
    package_name: str | None
    category: str | None
    design_id: uuid.UUID | None
    design_name: str | None
    design_image_url: str | None
    quantity: int
    reference_image_url: str | None
    note: str | None
    unit_price_min: float
    unit_price_max: float
    unit_advance: float
    unit_price: float | None

    class Config:
        from_attributes = True


class BulkOrderOut(BaseModel):
    id: uuid.UUID
    consumer_id: uuid.UUID
    status: str
    occasion: str
    event_at: datetime
    address_text: str
    location_lat: float | None
    location_lng: float | None
    gender_preference: str
    notes: str | None
    people: int
    lines: list[BulkOrderLineOut]
    # Range from the per-person bands, so the consumer sees what they'll pay
    # before (and after) the quote - recomputed with the current fee setting.
    estimate: EstimateOut
    subtotal: float | None
    platform_fee: float | None
    total_amount: float | None
    admin_note: str | None
    quoted_at: datetime | None
    confirmed_at: datetime | None
    cancel_reason: str | None
    advance_amount: float
    advance_status: str
    advance_paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminBulkOrderOut(BulkOrderOut):
    consumer_name: str | None
    consumer_phone: str
