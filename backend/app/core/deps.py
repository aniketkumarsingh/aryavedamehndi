import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.logging import user_id_var
from app.core.permissions import allowed, effective_role
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    request.state.user_id = str(user.id)  # for the access log line
    user_id_var.set(str(user.id))  # for log lines written while handling the request
    return user


def require_role(*roles: str):
    def dependency(request: Request, user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for this role")
        if user.role == "admin":
            # Marks the request for the audit log (main.py) and applies the
            # owner / ops / support policy.
            request.state.admin_role = effective_role(user.admin_role)
            if not allowed(user.admin_role, request.method, request.url.path):
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your admin role ({request.state.admin_role}) can't do this")
        return user

    return dependency
