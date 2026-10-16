import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import require_role
from app.database import get_db
from app.models.booking import Booking
from app.models.design import DesignUpload
from app.models.payment import Payment
from app.models.user import ArtistProfile, User
from app.schemas.payment import PaymentOrderOut, PaymentOut, PaymentVerifyIn
from app.services.notifications import notify
from app.services.razorpay_client import build_transfer, create_order, verify_payment_signature

router = APIRouter(prefix="/bookings/{booking_id}/payment", tags=["payments"])
settings = get_settings()

RELEASE_READY_STATUSES = {"auto_matched", "consumer_confirmed"}


@router.post("/order", response_model=PaymentOrderOut)
def create_payment_order(
    booking_id: uuid.UUID,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None or booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != "design_uploaded":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Design hasn't been uploaded yet")

    upload = db.query(DesignUpload).filter(DesignUpload.booking_id == booking_id).first()
    if upload is None or upload.match_status not in RELEASE_READY_STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Confirm the design first (POST design-confirm) before paying - payment can't unlock without it.",
        )

    artist_profile = db.get(ArtistProfile, booking.artist_id)
    linked_account = artist_profile.razorpay_linked_account_id if artist_profile else None

    payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if payment is None:
        payment = Payment(booking_id=booking_id, amount=0)
        db.add(payment)

    if linked_account:
        # Full escrow: consumer pays the whole booking amount, Razorpay
        # Route auto-splits it - the artist's share goes to their linked
        # account, the platform fee stays with the platform account.
        charge_amount = booking.total_amount
        transfers = [build_transfer(linked_account, booking.agreed_price)]
        order = create_order(charge_amount, receipt=str(booking.id), transfers=transfers)
        payment.is_full_escrow = True
        payment.artist_share = booking.agreed_price
        payment.platform_share = booking.platform_fee
        payment.payout_status = "pending"
    else:
        # Fallback: platform only collects its own fee; the package amount
        # is settled directly between consumer and artist outside the app
        # (see Booking.settlement_mode) until the artist has a payout
        # account set up.
        charge_amount = booking.platform_fee
        order = create_order(charge_amount, receipt=str(booking.id))
        payment.is_full_escrow = False
        payment.artist_share = None
        payment.platform_share = booking.platform_fee
        payment.payout_status = "not_applicable"

    payment.amount = charge_amount
    payment.razorpay_order_id = order["id"]
    payment.status = "created"
    db.commit()

    return PaymentOrderOut(
        booking_id=booking_id,
        razorpay_order_id=order["id"],
        razorpay_key_id=settings.razorpay_key_id or "dev_mode_no_key",
        amount=charge_amount,
        currency="INR",
        is_full_escrow=payment.is_full_escrow,
    )


@router.post("/verify", response_model=PaymentOut)
def verify_payment(
    booking_id: uuid.UUID,
    payload: PaymentVerifyIn,
    user: User = Depends(require_role("consumer")),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None or booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

    payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if payment is None or payment.razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching payment order")

    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        payment.status = "failed"
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    if payment.is_full_escrow:
        # Razorpay Route transfers the artist's share automatically as
        # part of settlement once the payment captures - nothing more to
        # trigger from here.
        payment.payout_status = "transferred"

    booking.status = "completed"
    notify(
        db,
        booking.artist_id,
        "payment",
        "Payment received",
        f"Booking completed - platform fee ₹{payment.amount} paid" + (", your share transferred" if payment.is_full_escrow else "."),
        f"/booking-detail/{booking_id}",
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.get("", response_model=PaymentOut)
def get_payment(booking_id: uuid.UUID, user: User = Depends(require_role("consumer")), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None or booking.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    payment = db.query(Payment).filter(Payment.booking_id == booking_id).first()
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payment yet")
    return payment
