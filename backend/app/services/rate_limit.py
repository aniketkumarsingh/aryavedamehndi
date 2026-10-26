"""Rate limiting on Postgres - fixed windows, no Redis needed.

Each check is one atomic upsert (INSERT ... ON CONFLICT DO UPDATE ...
RETURNING count) in its own short transaction, so it's safe across API
processes and isn't undone if the request later fails. Limits are set per
route in LIMITS and applied with `enforce(request, scope, *identities)`:
by client IP always, plus any extra identity (phone, user id) given.

Behind the reverse proxy, uvicorn runs with --proxy-headers so
request.client.host is the visitor's real IP, not the proxy's.
"""

import math
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.database import SessionLocal
from app.models.ops import RateLimitCounter
from app.services.jobs import job_handler, periodic

# scope -> (limit, window seconds) per IP, and per extra identity.
LIMITS: dict[str, dict[str, tuple[int, int]]] = {
    # SMS pumping: one address cycling through many phone numbers.
    "otp_request": {"ip": (10, 600), "id": (5, 3600)},
    "otp_verify": {"ip": (30, 600), "id": (10, 600)},
    "admin_login": {"ip": (10, 600), "id": (10, 600)},
    # Guessing coupon codes.
    "coupon_check": {"ip": (60, 600), "id": (30, 600)},
    "checkout": {"ip": (30, 600), "id": (10, 600)},
}

_UPSERT = text(
    """
    INSERT INTO rate_limit_counters (key, window_start, count) VALUES (:key, :window, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limit_counters.count + 1
    RETURNING count
    """
)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _window_start(now: datetime, seconds: int) -> datetime:
    epoch = datetime(1970, 1, 1)
    return epoch + timedelta(seconds=math.floor((now - epoch).total_seconds() / seconds) * seconds)


def hit(key: str, limit: int, window_seconds: int) -> int | None:
    """Counts one request; returns seconds to wait if over the limit."""
    now = utcnow()
    window = _window_start(now, window_seconds)
    with SessionLocal() as db:
        count = db.execute(_UPSERT, {"key": key[:200], "window": window}).scalar_one()
        db.commit()
    if count > limit:
        return max(1, int((window + timedelta(seconds=window_seconds) - now).total_seconds()))
    return None


def enforce(request: Request, scope: str, *identities: str | None) -> None:
    """Raises 429 (with Retry-After) when the client IP, or any of the
    given identities, has used up this scope's limit."""
    rules = LIMITS[scope]
    checks = [(f"{scope}:ip:{client_ip(request)}", *rules["ip"])]
    checks += [(f"{scope}:id:{identity}", *rules["id"]) for identity in identities if identity]
    waits = [w for key, limit, window in checks if (w := hit(key, limit, window))]
    if waits:
        wait = max(waits)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts - please try again in {math.ceil(wait / 60)} min",
            headers={"Retry-After": str(wait)},
        )


@job_handler("ops.rate_limit_cleanup")
def cleanup(db: Session, payload: dict) -> str:
    result = db.execute(delete(RateLimitCounter).where(RateLimitCounter.window_start < utcnow() - timedelta(days=1)))
    return f"{result.rowcount or 0} removed"


periodic("ops.rate_limit_cleanup", timedelta(hours=1))
