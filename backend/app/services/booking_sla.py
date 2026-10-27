"""Artist on-time watch for confirmed bookings (bookings.sla_check, every
10 minutes):
- an hour before the slot, remind the artist to set out on time;
- once the slot is past by the grace period (Settings, default 15 min) and
  they still haven't marked "on the way", alert admins and tell the
  customer we're on it. Each fires once per booking.
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.booking import Booking
from app.services.jobs import job_handler, periodic
from app.services.notifications import notify, notify_admins
from app.services.platform_settings import get_platform_settings

REMIND_BEFORE = timedelta(hours=1)


@job_handler("bookings.sla_check")
def sla_check(db: Session, payload: dict) -> str:
    now = utcnow()
    grace = timedelta(minutes=int(get_platform_settings(db)["booking_sla_grace_minutes"]))
    reminded = 0
    for booking in (
        db.query(Booking)
        .filter(Booking.status == "confirmed", Booking.artist_reminded_at.is_(None),
                Booking.scheduled_at <= now + REMIND_BEFORE, Booking.scheduled_at > now)
        .with_for_update(skip_locked=True)
        .all()
    ):
        notify(db, booking.artist_id, "booking", "Booking in an hour",
               'Your booking starts in about an hour - tap "On my way" when you set out.', f"/booking-detail/{booking.id}")
        booking.artist_reminded_at = now
        reminded += 1
    db.flush()
    late = (
        db.query(Booking)
        .filter(Booking.status == "confirmed", Booking.sla_alerted_at.is_(None), Booking.scheduled_at < now - grace)
        .with_for_update(skip_locked=True)
        .all()
    )
    for booking in late:
        minutes = int((now - booking.scheduled_at).total_seconds() // 60)
        notify_admins(db, "Artist not on the way",
                      f"Booking {str(booking.id)[:8]} started {minutes} min ago and the artist hasn't set out - call them.", "/admin")
        notify(db, booking.artist_id, "booking", "You're late", "Your booking has started - set out now or contact us.", f"/booking-detail/{booking.id}")
        notify(db, booking.consumer_id, "booking", "Checking on your artist",
               "Your artist hasn't set out yet - our team is contacting them and will update you.", f"/booking-detail/{booking.id}")
        booking.sla_alerted_at = now
    db.flush()
    return f"{reminded} reminded, {len(late)} late alerts"


periodic("bookings.sla_check", timedelta(minutes=10))
