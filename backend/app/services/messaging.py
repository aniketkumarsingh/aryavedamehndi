"""Lifecycle messaging: WhatsApp templates through MSG91, marketing consent
and unsubscribe links.

- Transactional messages (order/booking/shipping/refund updates) go to
  anyone with a phone number; promotional ones (cart reminders, occasion
  nudges) only to people who opted in (users.marketing_opt_in).
- Every send is a job ("messaging.whatsapp"), so a provider hiccup is
  retried and repeated failures appear under Admin -> Payments -> jobs.
- WhatsApp only sends Meta-approved templates. TEMPLATES below lists each
  template's name and its {{1}}, {{2}}... variables; their wording to submit
  for approval is in deploy/whatsapp_templates.md. Until
  MSG91_WHATSAPP_NUMBER is set, sends are skipped.
"""

import hashlib
import hmac
import logging

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import utcnow
from app.models.growth import ConsentRecord
from app.models.user import User
from app.services.jobs import enqueue, job_handler

log = logging.getLogger(__name__)
settings = get_settings()
MSG91_WHATSAPP_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

# template name -> (promotional?, variable names in order)
TEMPLATES: dict[str, tuple[bool, tuple[str, ...]]] = {
    "order_confirmed": (False, ("name", "order_ref", "amount")),
    "order_shipped": (False, ("name", "order_ref", "courier", "tracking")),
    "order_out_for_delivery": (False, ("name", "order_ref", "cod_note")),
    "order_delivered": (False, ("name", "order_ref")),
    "refund_processed": (False, ("name", "amount", "order_ref")),
    "booking_confirmed": (False, ("name", "artist", "when")),
    "artist_en_route": (False, ("name", "artist")),
    # Promotional templates end with an unsubscribe link (filled in automatically).
    "cart_reminder": (True, ("name", "link", "unsubscribe")),
    "cart_reminder_coupon": (True, ("name", "coupon", "percent", "link", "unsubscribe")),
    "occasion_nudge": (True, ("name", "occasion", "artist", "link", "unsubscribe")),
}


def whatsapp_enabled() -> bool:
    return bool(settings.msg91_auth_key and settings.msg91_whatsapp_number)


def _msisdn(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits if len(digits) > 10 else f"91{digits}"


def send_template(db: Session, user: User | None, template: str, params: dict, phone: str | None = None) -> bool:
    """Queues a WhatsApp template to a user (or a bare phone number).
    Returns False when it won't be sent (off, no phone, no consent)."""
    promotional, names = TEMPLATES[template]
    phone = phone or (user.phone if user else None)
    if not whatsapp_enabled() or not phone:
        return False
    if promotional and not (user and user.marketing_opt_in):
        return False
    if promotional:
        params = {**params, "unsubscribe": unsubscribe_link(user.id)}
    values = [str(params.get(n, ""))[:200] for n in names]
    enqueue(db, "messaging.whatsapp", {"to": _msisdn(phone), "template": template, "values": values}, max_attempts=5)
    return True


@job_handler("messaging.whatsapp")
def deliver_whatsapp(db: Session, payload: dict) -> str:
    if not whatsapp_enabled():
        return "skipped (WhatsApp not configured)"
    components = {f"body_{i}": {"type": "text", "value": v} for i, v in enumerate(payload["values"], start=1)}
    body = {
        "integrated_number": settings.msg91_whatsapp_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": {
                "name": payload["template"],
                "language": {"code": settings.whatsapp_language, "policy": "deterministic"},
                "to_and_components": [{"to": [payload["to"]], "components": components}],
            },
        },
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(MSG91_WHATSAPP_URL, json=body, headers={"authkey": settings.msg91_auth_key})
        resp.raise_for_status()  # retried with backoff by the job queue
    return f"sent {payload['template']}"


# ----------------------------------------------------------------- consent --

def set_marketing_consent(db: Session, user: User, granted: bool, source: str) -> None:
    """Records a change of marketing consent (no-op if unchanged)."""
    if bool(user.marketing_opt_in) == granted:
        return
    user.marketing_opt_in = granted
    user.marketing_opt_in_at = utcnow() if granted else None
    db.add(ConsentRecord(user_id=user.id, kind="marketing", granted=granted, source=source[:40]))


def unsubscribe_token(user_id) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"unsubscribe:{user_id}".encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_link(user_id) -> str:
    return f"{settings.public_site_url.rstrip('/')}/unsubscribe?u={user_id}&t={unsubscribe_token(user_id)}"


def verify_unsubscribe(user_id: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(user_id), token or "")


def whatsapp_user(db: Session, user_id, template: str, **params) -> bool:
    """send_template for a user id - the hook used at each lifecycle step."""
    user = db.get(User, user_id)
    if user is None:
        return False
    params.setdefault("name", (user.name or "there").split(" ")[0])
    return send_template(db, user, template, params)


def order_ref(order) -> str:
    return f"#{str(order.id)[:8].upper()}"
