"""A small, durable job queue on Postgres - no Redis or broker to run.

- `enqueue()` adds a job inside the caller's transaction (transactional
  outbox): the job exists only if the change that needed it commits.
- Workers (`python -m app.worker`) claim due jobs with
  SELECT ... FOR UPDATE SKIP LOCKED, so several can run side by side.
- A failing job is retried with exponential backoff and jitter; after
  `max_attempts` it's marked "dead" and admins are notified.
- A job left "running" by a crashed worker is put back after a timeout.
- Periodic tasks are enqueued with a dedupe key per time slot, so however
  many workers run, each slot runs once.
"""

import logging
import random
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.database import SessionLocal
from app.models.job import Job

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict], str | None]
HANDLERS: dict[str, Handler] = {}

STUCK_AFTER = timedelta(minutes=15)
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600


def job_handler(kind: str):
    """Registers a function as the handler for jobs of `kind`. It gets its
    own session (committed by the runner on success) and the job payload,
    and may return a short result string for the logs."""

    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def enqueue(
    db: Session,
    kind: str,
    payload: dict | None = None,
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 8,
) -> None:
    """Adds a job in the caller's transaction. With a dedupe_key, a second
    enqueue of the same key is silently ignored. Doesn't commit."""
    stmt = pg_insert(Job).values(
        kind=kind,
        payload=payload or {},
        run_at=run_at or utcnow(),
        dedupe_key=dedupe_key,
        max_attempts=max_attempts,
        status="queued",
        attempts=0,
        created_at=utcnow(),
    )
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["dedupe_key"])
    db.execute(stmt)


def backoff(attempts: int) -> timedelta:
    seconds = min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_CAP_SECONDS)
    return timedelta(seconds=seconds * random.uniform(0.8, 1.2))


@dataclass(frozen=True)
class ClaimedJob:
    id: object
    kind: str
    payload: dict
    attempts: int
    max_attempts: int


def _claim(worker_id: str, limit: int) -> list[ClaimedJob]:
    with SessionLocal() as db:
        jobs = db.scalars(
            select(Job)
            .where(Job.status == "queued", Job.run_at <= utcnow())
            .order_by(Job.run_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        claimed = []
        for job in jobs:
            job.status, job.locked_by, job.locked_at = "running", worker_id, utcnow()
            job.attempts += 1
            claimed.append(ClaimedJob(job.id, job.kind, dict(job.payload or {}), job.attempts, job.max_attempts))
        db.commit()
        return claimed


def _finish(job_id, **values) -> None:
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id).values(**values))
        db.commit()


def _run_one(job: ClaimedJob) -> None:
    from app.core.logging import job_var, order_id_var

    payload = job.payload or {}
    tokens = (job_var.set(f"{job.kind}:{job.id}"), order_id_var.set(payload.get("order_id") if isinstance(payload, dict) else None))
    try:
        _run_handler(job)
    finally:
        job_var.reset(tokens[0])
        order_id_var.reset(tokens[1])


def _run_handler(job: ClaimedJob) -> None:
    handler = HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise RuntimeError(f"No handler registered for job kind {job.kind!r}")
        with SessionLocal() as db:
            result = handler(db, job.payload or {})
            db.commit()
        _finish(job.id, status="done", finished_at=utcnow(), last_error=None, locked_by=None, locked_at=None)
        log.info("job %s %s done%s", job.kind, job.id, f": {result}" if result else "")
    except Exception as exc:  # noqa: BLE001 - every failure is recorded and retried
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"[:4000]
        if job.attempts >= job.max_attempts:
            _finish(job.id, status="dead", finished_at=utcnow(), last_error=error, locked_by=None, locked_at=None)
            log.error("job %s %s dead after %s attempts: %s", job.kind, job.id, job.attempts, exc)
            _alert_dead(job, exc)
            from app.core.observability import capture

            capture(exc, job_kind=job.kind, job_id=str(job.id))
        else:
            _finish(job.id, status="queued", run_at=utcnow() + backoff(job.attempts), last_error=error, locked_by=None, locked_at=None)
            log.warning("job %s %s failed (attempt %s/%s), will retry: %s", job.kind, job.id, job.attempts, job.max_attempts, exc)


def _alert_dead(job: ClaimedJob, exc: Exception) -> None:
    from app.services.notifications import notify_admins

    try:
        with SessionLocal() as db:
            notify_admins(db, "Background job failed", f"{job.kind} gave up after {job.attempts} attempts: {exc}"[:300], "/admin")
            db.commit()
    except Exception:  # noqa: BLE001 - alerting must never take the worker down
        log.exception("could not alert admins about dead job %s", job.id)


def requeue_stuck() -> int:
    """Puts back jobs a crashed worker left "running"."""
    with SessionLocal() as db:
        result = db.execute(
            update(Job)
            .where(Job.status == "running", Job.locked_at < utcnow() - STUCK_AFTER)
            .values(status="queued", locked_by=None, locked_at=None, run_at=utcnow())
        )
        db.commit()
        return result.rowcount or 0


def run_due_jobs(worker_id: str = "inline", limit: int = 20) -> int:
    """Runs up to `limit` due jobs, claiming each just before running it -
    a batch claimed up front could sit "running" behind a slow job long
    enough to look stuck and be run twice. Returns how many ran."""
    ran = 0
    while ran < limit:
        claimed = _claim(worker_id, 1)
        if not claimed:
            break
        _run_one(claimed[0])
        ran += 1
    return ran


def retry_job(db: Session, job: Job) -> None:
    """Admin action: give a dead job a fresh set of attempts now."""
    job.status, job.attempts, job.run_at, job.finished_at = "queued", 0, utcnow(), None


# ---------------------------------------------------------------- periodic --

@dataclass(frozen=True)
class Periodic:
    kind: str
    every: timedelta
    offset: timedelta = timedelta(0)  # shifts slot starts, e.g. a daily run at 21:00 UTC


PERIODIC: list[Periodic] = []


def periodic(kind: str, every: timedelta, offset: timedelta = timedelta(0)) -> None:
    PERIODIC.append(Periodic(kind, every, offset))


def enqueue_periodic(now: datetime | None = None) -> int:
    """Enqueues the current slot of every periodic task (once per slot)."""
    now = now or utcnow()
    epoch = datetime(1970, 1, 1)
    with SessionLocal() as db:
        for task in PERIODIC:
            elapsed = now - epoch - task.offset
            slot = int(elapsed / task.every)
            slot_start = epoch + task.offset + slot * task.every
            enqueue(db, task.kind, {"slot": slot_start.isoformat()}, run_at=slot_start, dedupe_key=f"periodic:{task.kind}:{slot}", max_attempts=3)
        db.commit()
    return len(PERIODIC)


@job_handler("jobs.cleanup")
def cleanup_jobs(db: Session, payload: dict) -> str:
    """Drops finished jobs after two weeks (dead ones are kept for review)."""
    result = db.execute(delete(Job).where(Job.status == "done", Job.finished_at < utcnow() - timedelta(days=14)))
    return f"{result.rowcount or 0} removed"


periodic("jobs.cleanup", timedelta(days=1), offset=timedelta(hours=20, minutes=30))  # 02:00 IST
