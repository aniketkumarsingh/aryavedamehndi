import uuid
from datetime import datetime

from pydantic import BaseModel


class PaymentOrderOut(BaseModel):
    booking_id: uuid.UUID
    razorpay_order_id: str
    razorpay_key_id: str
    amount: float
    currency: str
    is_full_escrow: bool
    # True when the paid advance covered the whole in-app amount, so the
    # booking completed without a Razorpay checkout.
    already_paid: bool = False


class PaymentVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    amount: float
    is_full_escrow: bool
    artist_share: float | None
    platform_share: float | None
    advance_credit: float
    platform_owes_artist: float
    payout_status: str
    currency: str
    status: str
    created_at: datetime
    paid_at: datetime | None

    class Config:
        from_attributes = True
