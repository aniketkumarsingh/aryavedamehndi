"""The one set of pricing rules for every way of ordering mehndi - a
regular booking, a booking for the consumer's own uploaded design, and a
bulk/event order. A person is always priced the same however they order:

- price band: a catalog design's own range replaces its package's; anything
  else (including a custom uploaded design) is priced at the package range.
- platform fee: compute_platform_fee on that one person's price.
- deposit: the package's advance_amount, per person.

A bulk order is just those per-person figures summed - no bulk surcharge
and no bulk discount (see order_estimate / quote_totals)."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.platform_settings import get_platform_settings


def compute_platform_fee(db: Session, agreed_price: float) -> float:
    values = get_platform_settings(db)
    if values["platform_fee_mode"] == "flat":
        return round(float(values["platform_fee_flat"]), 2)
    return round(agreed_price * float(values["platform_fee_percent"]) / 100, 2)


def price_band(package, design=None) -> tuple[float, float]:
    band = design or package
    return band.price_min, band.price_max


def check_price_in_band(package, amount: float, design=None) -> None:
    low, high = price_band(package, design)
    if not low <= amount <= high:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Price must be between ₹{low:g} and ₹{high:g} for this {'design' if design else 'package'}",
        )


def order_estimate(db: Session, lines) -> dict:
    """`lines` is (unit_price_min, unit_price_max, unit_advance, quantity)
    per kind of mehndi, the per-person figures from price_band and the
    package. Returns the range the order will cost - exactly what booking
    each person separately would cost."""
    subtotal_min = subtotal_max = fee_min = fee_max = advance = 0.0
    people = 0
    for low, high, unit_advance, quantity in lines:
        people += quantity
        subtotal_min += low * quantity
        subtotal_max += high * quantity
        fee_min += compute_platform_fee(db, low) * quantity
        fee_max += compute_platform_fee(db, high) * quantity
        advance += (unit_advance or 0) * quantity
    return {
        "people": people,
        "subtotal_min": round(subtotal_min, 2),
        "subtotal_max": round(subtotal_max, 2),
        "platform_fee_min": round(fee_min, 2),
        "platform_fee_max": round(fee_max, 2),
        "total_min": round(subtotal_min + fee_min, 2),
        "total_max": round(subtotal_max + fee_max, 2),
        "advance_amount": round(advance, 2),
    }


def quote_totals(db: Session, priced_lines) -> dict:
    """`priced_lines` is (unit_price, quantity) - each unit price already
    checked against its band. The fee is charged per person, as if each had
    booked on their own."""
    subtotal = sum(price * quantity for price, quantity in priced_lines)
    fee = sum(compute_platform_fee(db, price) * quantity for price, quantity in priced_lines)
    return {"subtotal": round(subtotal, 2), "platform_fee": round(fee, 2), "total_amount": round(subtotal + fee, 2)}


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
