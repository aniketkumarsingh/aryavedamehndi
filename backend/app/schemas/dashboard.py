import uuid
from datetime import datetime

from pydantic import BaseModel


class SettlementModeBreakdown(BaseModel):
    mode: str
    count: int
    total_amount: float


class TransactionOut(BaseModel):
    id: uuid.UUID
    status: str
    package_name: str
    scheduled_at: datetime
    agreed_price: float | None
    platform_fee: float | None
    settlement_mode: str | None
    settlement_recorded_at: datetime | None


class ArtistDashboardOut(BaseModel):
    orders_taken: int
    orders_completed: int
    orders_missed: int  # cancelled + disputed - orders that didn't go through
    rating_avg: float
    rating_count: int
    total_earnings: float
    settlement_breakdown: list[SettlementModeBreakdown]
    recent_transactions: list[TransactionOut]


class SettlementIn(BaseModel):
    mode: str  # "upi" | "cash" | "bank_transfer" | "other"


class ConsumerRecentBookingOut(BaseModel):
    id: uuid.UUID
    status: str
    package_name: str
    artist_name: str | None
    scheduled_at: datetime
    total_amount: float | None


class ProfileCompletionOut(BaseModel):
    has_name: bool
    has_gender: bool
    has_avatar: bool
    percent: int


class ConsumerDashboardOut(BaseModel):
    total_bookings: int
    upcoming_bookings: int
    completed_bookings: int
    profile_completion: ProfileCompletionOut
    recent_bookings: list[ConsumerRecentBookingOut]
