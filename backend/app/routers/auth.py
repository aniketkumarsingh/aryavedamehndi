from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AdminLoginIn, RefreshIn, RequestOtpIn, RequestOtpOut, TokenOut, VerifyOtpIn
from app.services.auth_tokens import InvalidRefreshToken, issue_token_pair, revoke_refresh_token, rotate_refresh_token
from app.services.otp import OtpRateLimited, issue_otp, verify_otp
from app.services.rate_limit import enforce
from app.core.time import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


@router.post("/request-otp", response_model=RequestOtpOut)
def request_otp(payload: RequestOtpIn, request: Request, db: Session = Depends(get_db)):
    enforce(request, "otp_request", payload.phone)
    try:
        code, sent = issue_otp(db, payload.phone)
    except OtpRateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    return RequestOtpOut(sent_by_sms=sent, dev_otp=None if sent else code)


@router.post("/admin-login", response_model=TokenOut)
def admin_login(payload: AdminLoginIn, request: Request, db: Session = Depends(get_db)):
    """Traditional username/password login, admin-only - a convenience
    alternative to phone-OTP so the business owner doesn't need a
    registered phone number to reach the admin panel. Generic error
    messages throughout (don't reveal whether the username exists) plus a
    lockout after repeated failures, same spirit as the OTP rate limiting
    in app/services/otp.py."""
    enforce(request, "admin_login", payload.username.lower())
    generic_error = "Invalid username or password"
    user = db.query(User).filter(User.username == payload.username, User.role == "admin").first()
    if user is None or not user.password_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    if user.locked_until and user.locked_until > utcnow():
        wait_minutes = max(1, round((user.locked_until - utcnow()).total_seconds() / 60))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many failed attempts - try again in {wait_minutes} min")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generic_error)

    user.failed_login_count = 0
    user.locked_until = None
    access, refresh = issue_token_pair(db, user)
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh, user_id=user.id, role=user.role, is_new_user=False)


@router.post("/verify-otp", response_model=TokenOut)
def verify_otp_and_login(payload: VerifyOtpIn, request: Request, db: Session = Depends(get_db)):
    enforce(request, "otp_verify", payload.phone)
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

    access, refresh = issue_token_pair(db, user)
    db.commit()
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        role=user.role,
        is_new_user=is_new_user,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh_tokens(payload: RefreshIn, db: Session = Depends(get_db)):
    """Swaps a refresh token for a new access + refresh pair (rotation -
    the old refresh token stops working). See app/services/auth_tokens.py."""
    try:
        user, access, refresh = rotate_refresh_token(db, payload.refresh_token)
    except InvalidRefreshToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return TokenOut(access_token=access, refresh_token=refresh, user_id=user.id, role=user.role, is_new_user=False)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshIn, db: Session = Depends(get_db)):
    revoke_refresh_token(db, payload.refresh_token)
