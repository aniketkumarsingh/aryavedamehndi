"""Idempotency keys for requests that create things (Stripe-style).

A client sends `Idempotency-Key: <uuid>` with the request. The key row is
inserted in the same transaction as the work:
- first request: the insert succeeds, the work runs, the response is stored
  with the key, and both commit together (or both roll back on an error,
  freeing the key for a retry);
- a concurrent duplicate blocks on the unique key until the first commits,
  then gets the stored response replayed;
- the same key with a different body is refused (409).
Keys are kept for 24 hours.
"""

import hashlib
import json

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.payment_ops import IdempotencyKey


def _hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def claim(db: Session, user_id, scope: str, key: str, body: dict) -> JSONResponse | None:
    """Reserves the key, or returns the stored response to replay."""
    if not key or len(key) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key must be 1-100 characters")
    request_hash = _hash(body)
    inserted = db.execute(
        pg_insert(IdempotencyKey)
        .values(user_id=user_id, scope=scope, key=key, request_hash=request_hash, created_at=utcnow())
        .on_conflict_do_nothing(constraint="uq_idempotency_user_scope_key")
        .returning(IdempotencyKey.id)
    ).first()
    if inserted:
        return None
    row = db.query(IdempotencyKey).filter_by(user_id=user_id, scope=scope, key=key).one()
    if row.request_hash != request_hash:
        raise HTTPException(status.HTTP_409_CONFLICT, "This Idempotency-Key was already used for a different request")
    if row.status_code is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The original request is still being processed - try again shortly")
    return JSONResponse(row.response, status_code=row.status_code, headers={"Idempotent-Replayed": "true"})


def store(db: Session, user_id, scope: str, key: str, status_code: int, response: dict) -> None:
    db.query(IdempotencyKey).filter_by(user_id=user_id, scope=scope, key=key).update({"status_code": status_code, "response": response})
