"""Data protection (DPDP Act): self-serve account deletion, a copy of your
data, and retention clean-up.

Deleting an account anonymises the person rather than removing rows, so
orders, invoices, payouts and reviews stay consistent:
- name, phone, photos, dates, guardian/emergency contacts, marketing and
  analytics choices, attribution and referral code are cleared; the phone is
  replaced so the number can sign up afresh;
- an artist's ID, PAN and bank details, documents, address and map point are
  cleared and the profile is suspended;
- addresses on bookings, event requests and shop orders are cleared - except
  shop orders with a GST invoice, whose billing details must be kept for the
  statutory period (8 years);
- their chat messages are blanked, sessions revoked, and the request logged
  as a consent withdrawal.
Not possible while a booking, event request or shop order is still open.

privacy.retention (daily) removes what's no longer needed: OTP codes after a
day, rate-limit counters after two, finished jobs after 30 days, webhook
payloads after 180 days, read notifications after a year, carts untouched
for 90 days; KYC documents and ID/PAN numbers of artists whose KYC was
rejected and not resubmitted, 90 days after the rejection (approved
artists keep theirs while they work with us - the verification record);
chat messages of finished bookings after 180 days (2 years when the booking
had a dispute, as evidence).
"""

import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.booking import Booking
from app.models.bulk_order import BulkOrder
from app.models.chat import ChatMessage
from app.models.growth import Cart, ConsentRecord, Referral, WalletEntry
from app.models.job import Job
from app.models.notification import Notification
from app.models.ops import RateLimitCounter
from app.models.otp import OtpCode
from app.models.payment_ops import PaymentEvent
from app.models.shipping import ShippingWebhookEvent
from app.models.shop import ShopOrder
from app.models.user import ArtistProfile, User
from app.services.auth_tokens import revoke_all_for_user
from app.services.jobs import job_handler, periodic
from app.services.storage import delete_media

OPEN_BOOKING = ("requested", "negotiating", "confirmed", "artist_enroute", "arrived", "in_progress", "design_uploaded", "disputed")
CLOSED_BULK = ("completed", "cancelled")
OPEN_SHOP = ("pending", "confirmed", "shipped")
ARTIST_PRIVATE_FIELDS = (
    "date_of_birth", "guardian_name", "emergency_contact_name", "emergency_contact_phone", "address_text", "base_lat", "base_lng",
    "kyc_selfie_url", "id_proof_number", "id_proof_doc_url", "pan_number", "pan_doc_url", "address_proof_doc_url",
    "bank_account_number", "bank_ifsc_code", "bank_account_holder_name", "profile_photo_url", "portfolio_urls", "bio",
)
REMOVED = "[removed]"
KYC_DOC_FIELDS = ("kyc_selfie_url", "id_proof_doc_url", "pan_doc_url", "address_proof_doc_url")
KYC_REJECTED_DAYS = 90
CHAT_DAYS = 180
DISPUTED_CHAT_DAYS = 730


class PrivacyError(Exception):
    pass


def open_items(db: Session, user: User) -> list[str]:
    reasons = []
    as_artist = Booking.artist_id == user.id
    if db.query(Booking.id).filter(or_(Booking.consumer_id == user.id, as_artist), Booking.status.in_(OPEN_BOOKING)).first():
        reasons.append("a booking that isn't finished")
    if db.query(BulkOrder.id).filter(BulkOrder.consumer_id == user.id, BulkOrder.status.notin_(CLOSED_BULK)).first():
        reasons.append("an event request that isn't finished")
    if db.query(ShopOrder.id).filter(ShopOrder.consumer_id == user.id, ShopOrder.status.in_(OPEN_SHOP)).first():
        reasons.append("a shop order on its way")
    return reasons


def delete_account(db: Session, user: User, source: str = "self_service") -> None:
    """Anonymises the account (see module docstring). Doesn't commit."""
    if user.role == "admin":
        raise PrivacyError("Admin accounts are removed from Admin → Team")
    if reasons := open_items(db, user):
        raise PrivacyError("Your account can be deleted once you have no " + " or ".join(reasons))
    now = utcnow()
    db.add(ConsentRecord(id=uuid.uuid4(), user_id=user.id, kind="marketing", granted=False, source="account_deleted"))
    db.add(ConsentRecord(id=uuid.uuid4(), user_id=user.id, kind="analytics", granted=False, source="account_deleted"))
    user.name = "Deleted user"
    user.phone = f"x{user.id.hex[:14]}"  # frees the real number; unique per account
    for field in ("avatar_url", "guardian_name", "secondary_phone", "date_of_birth", "anniversary_date", "attribution", "referral_code",
                  "marketing_opt_in_at"):
        setattr(user, field, None)
    user.marketing_opt_in = user.analytics_consent = False
    user.is_active, user.deleted_at = False, now
    if getattr(user, "username", None):
        user.username = None

    profile = db.get(ArtistProfile, user.id)
    if profile is not None:
        for field in ARTIST_PRIVATE_FIELDS:
            setattr(profile, field, None)
        profile.is_suspended = True

    for booking in db.query(Booking).filter(Booking.consumer_id == user.id):
        booking.address_text = REMOVED
    for bulk in db.query(BulkOrder).filter(BulkOrder.consumer_id == user.id):
        bulk.address_text, bulk.notes = REMOVED, None
    for order in db.query(ShopOrder).filter(ShopOrder.consumer_id == user.id):
        order.attribution = None
        if not order.invoice_number:  # invoiced orders keep billing details (GST records)
            order.shipping_name, order.shipping_phone, order.shipping_address = REMOVED, REMOVED, REMOVED
            order.contact_email = None
    db.query(ChatMessage).filter(ChatMessage.sender_id == user.id).update({ChatMessage.body: REMOVED}, synchronize_session=False)
    cart = db.get(Cart, user.id)
    if cart is not None:
        cart.items = []
    revoke_all_for_user(db, user.id)


def export_data(db: Session, user: User) -> dict:
    """Everything we hold about the person, as JSON (right to access)."""
    def rows(q, *fields):
        return [{f: getattr(r, f) for f in fields} for r in q]

    profile = db.get(ArtistProfile, user.id)
    return {
        "exported_at": utcnow(),
        "account": {f: getattr(user, f) for f in ("id", "phone", "name", "role", "gender", "date_of_birth", "anniversary_date",
                                                   "guardian_name", "secondary_phone", "marketing_opt_in", "analytics_consent",
                                                   "attribution", "referral_code", "created_at")},
        "artist_profile": {f: getattr(profile, f) for f in ("bio", "city", "service_radius_km", "address_text", "kyc_status",
                                                            "id_proof_type", "pan_number", "bank_account_holder_name")} if profile else None,
        "bookings": rows(db.query(Booking).filter(or_(Booking.consumer_id == user.id, Booking.artist_id == user.id)),
                         "id", "status", "scheduled_at", "address_text", "created_at"),
        "event_requests": rows(db.query(BulkOrder).filter(BulkOrder.consumer_id == user.id), "id", "status", "occasion", "event_at", "address_text"),
        "shop_orders": rows(db.query(ShopOrder).filter(ShopOrder.consumer_id == user.id), "id", "status", "total_amount",
                            "shipping_name", "shipping_phone", "shipping_address", "created_at"),
        "consents": rows(db.query(ConsentRecord).filter(ConsentRecord.user_id == user.id).order_by(ConsentRecord.created_at),
                         "kind", "granted", "source", "created_at"),
        "wallet": rows(db.query(WalletEntry).filter(WalletEntry.user_id == user.id).order_by(WalletEntry.created_at),
                       "kind", "amount", "note", "created_at"),
        "referrals_made": db.query(Referral).filter(Referral.referrer_id == user.id).count(),
        "chat_messages_sent": db.query(ChatMessage).filter(ChatMessage.sender_id == user.id).count(),
    }


@job_handler("privacy.retention")
def retention_job(db: Session, payload: dict) -> str:
    now = utcnow()
    done = {
        "otp": db.query(OtpCode).filter(OtpCode.created_at < now - timedelta(days=1)).delete(synchronize_session=False),
        "rate_limits": db.query(RateLimitCounter).filter(RateLimitCounter.window_start < now - timedelta(days=2)).delete(synchronize_session=False),
        "jobs": db.query(Job).filter(Job.status == "done", Job.finished_at < now - timedelta(days=30)).delete(synchronize_session=False),
        "notifications": db.query(Notification).filter(Notification.is_read.is_(True), Notification.created_at < now - timedelta(days=365))
        .delete(synchronize_session=False),
    }
    old = now - timedelta(days=180)
    done["payment_payloads"] = (db.query(PaymentEvent).filter(PaymentEvent.received_at < old, PaymentEvent.status == "processed",
                                                             PaymentEvent.payload != {})
                                .update({PaymentEvent.payload: {}}, synchronize_session=False))
    done["shipping_payloads"] = (db.query(ShippingWebhookEvent).filter(ShippingWebhookEvent.received_at < old, ShippingWebhookEvent.status == "processed")
                                 .update({ShippingWebhookEvent.payload: {}}, synchronize_session=False))
    done["carts"] = 0
    for cart in db.query(Cart).filter(Cart.updated_at < now - timedelta(days=90)):
        if cart.items:
            cart.items = []
            done["carts"] += 1

    done["rejected_kyc"] = 0
    rejected = db.query(ArtistProfile).filter(ArtistProfile.kyc_status == "rejected",
                                              ArtistProfile.kyc_reviewed_at < now - timedelta(days=KYC_REJECTED_DAYS))
    for profile in rejected:
        urls = [getattr(profile, f) for f in KYC_DOC_FIELDS if getattr(profile, f)]
        if not urls and not profile.id_proof_number and not profile.pan_number:
            continue
        for url in urls:
            try:
                delete_media(url)
            except Exception:  # noqa: BLE001 - the record is cleared even if a file is already gone
                pass
        for field in (*KYC_DOC_FIELDS, "id_proof_number", "pan_number"):
            setattr(profile, field, None)
        done["rejected_kyc"] += 1

    finished = Booking.status.in_(("completed", "cancelled"))
    old_chats = select(Booking.id).where(finished, or_(
        and_(Booking.dispute_resolved_at.is_(None), Booking.scheduled_at < now - timedelta(days=CHAT_DAYS)),
        Booking.dispute_resolved_at < now - timedelta(days=DISPUTED_CHAT_DAYS),
    ))
    done["chat_messages"] = db.query(ChatMessage).filter(ChatMessage.booking_id.in_(old_chats)).delete(synchronize_session=False)
    db.flush()
    return ", ".join(f"{k} {v}" for k, v in done.items())


periodic("privacy.retention", timedelta(days=1), offset=timedelta(hours=2, minutes=30))
