"""Access/refresh token issuing with refresh-token rotation.

Every refresh revokes the presented refresh token and issues a fresh
pair. If an already-revoked refresh token is presented again, someone is
replaying a stolen copy, so every outstanding refresh token for that user
is revoked and they have to log in again."""

import uuid

from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.core.time import utcnow


class InvalidRefreshToken(Exception):
    pass


def issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    """Returns (access_token, refresh_token). Doesn't commit."""
    refresh, jti, expires_at = create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at.replace(tzinfo=None)))
    return create_access_token(user.id, user.role), refresh


def rotate_refresh_token(db: Session, token: str) -> tuple[User, str, str]:
    """Validates and consumes a refresh token. Commits (a detected replay
    must revoke the user's tokens even though the request then fails)."""
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise InvalidRefreshToken(str(exc)) from exc
    if payload.get("type") != "refresh" or not payload.get("jti"):
        raise InvalidRefreshToken("Wrong token type")

    row = db.get(RefreshToken, payload["jti"])
    if row is None or str(row.user_id) != payload["sub"]:
        raise InvalidRefreshToken("Unknown refresh token")

    now = utcnow()
    if row.revoked_at is not None:
        revoke_all_for_user(db, row.user_id)
        db.commit()
        raise InvalidRefreshToken("Refresh token was already used - please log in again")

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise InvalidRefreshToken("User not found or inactive")

    row.revoked_at = now
    access, refresh = issue_token_pair(db, user)
    db.commit()
    return user, access, refresh


def revoke_refresh_token(db: Session, token: str) -> None:
    """Logout - revokes one refresh token if it's valid; silently ignores
    anything else so logout always succeeds client-side."""
    try:
        payload = decode_token(token)
    except ValueError:
        return
    row = db.get(RefreshToken, payload.get("jti") or "")
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).update(
        {"revoked_at": utcnow()}
    )
