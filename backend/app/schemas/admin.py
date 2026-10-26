import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.review import ReportOut


class AdminOverviewOut(BaseModel):
    total_consumers: int
    total_artists: int
    approved_artists: int
    pending_kyc_count: int
    total_bookings: int
    completed_bookings: int
    open_reports_count: int
    total_platform_revenue: float


class AdminBookingOut(BaseModel):
    id: uuid.UUID
    status: str
    package_name: str
    consumer_name: str | None
    consumer_phone: str
    artist_name: str | None
    artist_phone: str
    scheduled_at: datetime
    total_amount: float | None
    arrival_distance_m: float | None = None
    arrival_flagged: bool = False
    created_at: datetime


class AdminDisputeOut(BaseModel):
    booking: AdminBookingOut
    reference_image_url: str | None
    completed_image_url: str | None
    similarity_score: float | None
    match_status: str | None
    advance_amount: float
    advance_status: str
    reports: list[ReportOut]


class DisputeResolveIn(BaseModel):
    # "released" - consumer can pay and complete as normal
    # "cancelled" - no platform fee, paid advance refunded
    outcome: Literal["released", "cancelled"]
    notes: str | None = Field(default=None, max_length=2000)


class PlatformSettingsOut(BaseModel):
    platform_fee_mode: Literal["percent", "flat"]
    platform_fee_percent: float
    platform_fee_flat: float
    design_match_threshold: int
    strikes_before_suspension: int
    checkin_flag_distance_m: int
    shop_shipping_fee: float
    shop_free_shipping_above: float
    shop_payment_window_minutes: int


class PlatformSettingsIn(BaseModel):
    platform_fee_mode: Literal["percent", "flat"] | None = None
    platform_fee_percent: float | None = Field(default=None, ge=0, le=50)
    platform_fee_flat: float | None = Field(default=None, ge=0, le=100_000)
    design_match_threshold: int | None = Field(default=None, ge=0, le=100)
    strikes_before_suspension: int | None = Field(default=None, ge=1, le=20)
    checkin_flag_distance_m: int | None = Field(default=None, ge=50, le=50_000)
    shop_shipping_fee: float | None = Field(default=None, ge=0, le=10_000)
    shop_free_shipping_above: float | None = Field(default=None, ge=0, le=1_000_000)
    shop_payment_window_minutes: int | None = Field(default=None, ge=10, le=24 * 60)


class AdminUserOut(BaseModel):
    id: uuid.UUID
    phone: str
    name: str | None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminArtistOut(BaseModel):
    user_id: uuid.UUID
    name: str | None
    phone: str
    profile_photo_url: str | None
    kyc_status: str
    is_suspended: bool
    is_active: bool
    strike_count: int
    rating_avg: float
    rating_count: int
    completed_bookings: int
    total_earnings: float
