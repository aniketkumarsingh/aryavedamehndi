import uuid

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
from app.services.pricing import settlement_breakdown
from app.services.razorpay_client import build_transfer, create_order, verify_payment_signature
from app.core.time import utcnow

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
    elif payment.status == "paid":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This booking is already paid")

    # The paid advance is credited against this charge - see
    # pricing.settlement_breakdown.
    split = settlement_breakdown(booking, full_escrow=bool(linked_account))
    charge_amount = split["in_app_due"]
    payment.advance_credit = split["advance_credit"]
    payment.platform_owes_artist = split["platform_owes_artist"]
    payment.platform_share = booking.platform_fee

    if linked_account:
        # Full escrow: consumer pays the whole booking amount (less the
        # advance), Razorpay Route auto-splits it - the artist's share goes
        # to their linked account, the platform fee stays with the platform.
        transfers = [build_transfer(linked_account, split["artist_transfer"])] if split["artist_transfer"] > 0 else None
        payment.is_full_escrow = True
        payment.artist_share = split["artist_transfer"]
        payment.payout_status = "pending"
    else:
        # Fallback: platform only collects its own fee; the package amount
        # is settled directly between consumer and artist outside the app
        # (see Booking.settlement_mode) until the artist has a payout
        # account set up.
        transfers = None
        payment.is_full_escrow = False
        payment.artist_share = None
        payment.payout_status = "not_applicable"

    payment.amount = charge_amount

    if charge_amount <= 0:
        # The advance already covered everything due in-app - there's
        # nothing to charge (Razorpay rejects zero-amount orders), so the
        # booking completes straight away.
        payment.razorpay_order_id = None
        _mark_paid(db, booking, payment)
        db.commit()
        return PaymentOrderOut(
            booking_id=booking_id,
            razorpay_order_id="",
            razorpay_key_id=settings.razorpay_key_id or "dev_mode_no_key",
            amount=0,
            currency="INR",
            is_full_escrow=payment.is_full_escrow,
            already_paid=True,
        )

    order = create_order(charge_amount, receipt=str(booking.id), transfers=transfers)
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


def _mark_paid(db: Session, booking: Booking, payment: Payment) -> None:
    payment.status = "paid"
    payment.paid_at = utcnow()
    if payment.is_full_escrow:
        # Razorpay Route transfers the artist's share automatically as
        # part of settlement once the payment captures - nothing more to
        # trigger from here.
        payment.payout_status = "transferred"

    booking.status = "completed"
    body = f"Booking completed - ₹{payment.amount} paid in-app"
    if payment.advance_credit:
        body += f" (₹{payment.advance_credit} advance credited)"
    if payment.is_full_escrow:
        body += ", your share transferred"
    if payment.platform_owes_artist:
        body += f". ₹{payment.platform_owes_artist} of the advance will be paid out to you"
    notify(db, booking.artist_id, "payment", "Payment received", body + ".", f"/booking-detail/{booking.id}")


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
    if payment is None or not payment.razorpay_order_id or payment.razorpay_order_id != payload.razorpay_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No matching payment order")
    if payment.status == "paid":
        # Idempotent - e.g. the Razorpay success handler firing twice.
        return payment
    if booking.status != "design_uploaded":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This booking isn't awaiting payment")

    if not verify_payment_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        payment.status = "failed"
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")

    payment.razorpay_payment_id = payload.razorpay_payment_id
    payment.razorpay_signature = payload.razorpay_signature
    _mark_paid(db, booking, payment)
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
