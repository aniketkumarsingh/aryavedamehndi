"""Imports every module that registers job handlers or periodic tasks, so
the worker (and tests) know all of them."""

from datetime import timedelta

from app.core.time import utcnow
from app.models.payment_ops import IdempotencyKey
from app.services import email, jobs, payment_events, reconciliation, refunds, shop_orders  # noqa: F401
from app.services.jobs import job_handler, periodic


@job_handler("idempotency.cleanup")
def cleanup_idempotency_keys(db, payload):
    removed = db.query(IdempotencyKey).filter(IdempotencyKey.created_at < utcnow() - timedelta(days=1)).delete()
    return f"{removed} removed"


periodic("idempotency.cleanup", timedelta(hours=6))
