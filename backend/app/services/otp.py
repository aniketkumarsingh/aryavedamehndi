import random
import string
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.otp import OtpCode

settings = get_settings()

OTP_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
REQUEST_COOLDOWN_SECONDS = 45
MAX_REQUESTS_PER_HOUR = 8


class OtpRateLimited(Exception):
    """Raised when a phone number is requesting OTPs too fast - protects
    against SMS-bombing a victim's phone and against running up SMS costs."""


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def issue_otp(db: Session, phone: str) -> tuple[str, bool]:
    """Create an OTP row and (in production) send it by SMS.

    Returns (code, sent_by_sms). In dev mode the code is not sent and is
    returned to the caller so it can be surfaced in the API response.

    Raises OtpRateLimited if this phone number has requested codes too
    often recently.
    """
    now = datetime.utcnow()
    recent = db.query(OtpCode).filter(OtpCode.phone == phone, OtpCode.created_at >= now - timedelta(hours=1)).all()
    if recent:
        most_recent = max(o.created_at for o in recent)
        if (now - most_recent).total_seconds() < REQUEST_COOLDOWN_SECONDS:
            raise OtpRateLimited(f"Please wait before requesting another OTP for {phone}")
        if len(recent) >= MAX_REQUESTS_PER_HOUR:
            raise OtpRateLimited(f"Too many OTP requests for {phone} in the last hour")

    code = _generate_code()
    otp = OtpCode(
        phone=phone,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(otp)
    db.commit()

    if settings.otp_dev_mode or not settings.msg91_auth_key:
        print(f"[dev-otp] phone={phone} code={code}")
        return code, False

    _send_via_msg91(phone, code)
    return code, True


def _send_via_msg91(phone: str, code: str) -> None:
    url = "https://control.msg91.com/api/v5/otp"
    params = {
        "authkey": settings.msg91_auth_key,
        "mobile": phone,
        "otp": code,
        "sender": settings.msg91_sender_id,
        "template_id": settings.msg91_otp_template_id,
    }
    with httpx.Client(timeout=10) as client:
        client.post(url, params=params)


def verify_otp(db: Session, phone: str, code: str) -> bool:
    otp = (
        db.query(OtpCode)
        .filter(OtpCode.phone == phone, OtpCode.is_used.is_(False))
        .order_by(OtpCode.created_at.desc())
        .first()
    )
    if otp is None:
        return False
    if otp.expires_at < datetime.utcnow():
        return False
    if otp.attempts >= MAX_ATTEMPTS:
        return False

    otp.attempts += 1
    if otp.code != code:
        db.commit()
        return False

    otp.is_used = True
    db.commit()
    return True
