from sqlalchemy.orm import Session

from app.services.platform_settings import get_platform_settings


def compute_platform_fee(db: Session, agreed_price: float) -> float:
    values = get_platform_settings(db)
    if values["platform_fee_mode"] == "flat":
        return round(float(values["platform_fee_flat"]), 2)
    return round(agreed_price * float(values["platform_fee_percent"]) / 100, 2)


def settlement_breakdown(booking, full_escrow: bool) -> dict:
    """How the final payment splits once the paid advance is credited.

    The advance went to the platform's Razorpay account, but it's part of
    what the consumer owes for the booking, so it's subtracted from the
    final in-app charge:

    - full escrow (artist has a Route account): the consumer pays
      package + fee - advance in-app, and the artist's share is transferred
      from that order (capped at the order amount).
    - fee-only: the consumer pays fee - advance in-app and the package
      price directly to the artist.

    Whatever part of the advance the in-app charge can't absorb belongs to
    the artist and comes back as `platform_owes_artist` for ops to pay out
    (and, in fee-only mode, is knocked off what the consumer pays the
    artist directly).
    """
    price = booking.agreed_price or 0
    fee = booking.platform_fee or 0
    advance = booking.advance_amount if booking.advance_status == "paid" else 0

    if full_escrow:
        in_app_due = round(max(0.0, price + fee - advance), 2)
        artist_transfer = round(min(price, in_app_due), 2)
        platform_owes_artist = round(price - artist_transfer, 2)
        artist_direct_due = 0.0
    else:
        in_app_due = round(max(0.0, fee - advance), 2)
        artist_transfer = 0.0
        platform_owes_artist = round(max(0.0, advance - fee), 2)
        artist_direct_due = round(max(0.0, price - platform_owes_artist), 2)

    return {
        "in_app_due": in_app_due,
        "advance_credit": round(advance, 2),
        "artist_transfer": artist_transfer,
        "artist_direct_due": artist_direct_due,
        "platform_owes_artist": platform_owes_artist,
    }
