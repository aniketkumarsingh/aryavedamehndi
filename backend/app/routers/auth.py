from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AdminLoginIn, RequestOtpIn, RequestOtpOut, TokenOut, VerifyOtpIn
from app.services.otp import OtpRateLimited, issue_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@router.post("/request-otp", response_model=RequestOtpOut)
def request_otp(payload: RequestOtpIn, db: Session = Depends(get_db)):
    try:
        code, sent = issue_otp(db, payload.phone)
    except OtpRateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    return RequestOtpOut(sent_by_sms=sent, dev_otp=None if sent else code)


@router.post("/admin-login", response_model=TokenOut)
def admin_login(payload: AdminLoginIn, db: Session = Depends(get_db)):
    """Traditional username/password login, admin-only - a convenience
    alternative to phone-OTP so the business owner doesn't need a
    registered phone number to reach the admin panel. Generic error
    messages throughout (don't reveal whether the username exists) plus a
    lockout after repeated failures, same spirit as the OTP rate limiting
    in app/services/otp.py."""
    generic_error = "Invalid username or password"
    user = db.query(User).filter(User.username == payload.username, User.role == "admin").first()
    if user is None or not user.password_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    if user.locked_until and user.locked_until > datetime.utcnow():
        wait_minutes = max(1, round((user.locked_until - datetime.utcnow()).total_seconds() / 60))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many failed attempts - try again in {wait_minutes} min")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenOut(access_token=access, refresh_token=refresh, user_id=user.id, role=user.role, is_new_user=False)


@router.post("/verify-otp", response_model=TokenOut)
def verify_otp_and_login(payload: VerifyOtpIn, db: Session = Depends(get_db)):
    if not verify_otp(db, payload.phone, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OTP")

    user = db.query(User).filter(User.phone == payload.phone).first()
    is_new_user = user is None
    if user is None:
        user = User(
            phone=payload.phone,
            role=payload.role if payload.role in ("consumer", "artist") else "consumer",
            name=payload.name,
            gender=payload.gender,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        role=user.role,
        is_new_user=is_new_user,
    )
