"""The admin audit log: changes, refused attempts and data exports by admins
(recorded by the request middleware in main.py, after the response)."""

import logging
import uuid

from app.database import SessionLocal
from app.models.admin_ops import AdminAuditLog

log = logging.getLogger(__name__)
EXPORT_SUFFIXES = (".csv", ".pdf")


def needs_audit(method: str, path: str, status_code: int) -> bool:
    return method not in ("GET", "HEAD", "OPTIONS") or status_code == 403 or path.endswith(EXPORT_SUFFIXES)


def record_admin_action(admin_id, admin_role, method, path, query, status_code, request_id, ip) -> None:
    try:
        with SessionLocal() as db:
            db.add(AdminAuditLog(
                id=uuid.uuid4(), admin_id=uuid.UUID(admin_id) if admin_id else None, admin_role=admin_role,
                method=method, path=path[:300], query=(query or "")[:500] or None, status_code=status_code,
                request_id=request_id, ip=ip,
            ))
            db.commit()
    except Exception:  # noqa: BLE001 - never fail a request over its audit line
        log.exception("could not write the admin audit log")
