import uuid
from datetime import datetime

from pydantic import BaseModel


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
    created_at: datetime


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
