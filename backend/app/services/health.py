"""Readiness checks behind GET /health/ready (point the uptime monitor here)."""

from datetime import timedelta

from sqlalchemy import func, text

from app.config import get_settings
from app.core.time import utcnow
from app.database import SessionLocal
from app.models.job import Job

settings = get_settings()

QUEUE_LAG_LIMIT = timedelta(minutes=10)
# shop.release_unpaid finishes every 5 minutes, so a worker that's alive
# always has a recent finished job.
WORKER_SILENT_LIMIT = timedelta(minutes=20)
BACKUP_AGE_LIMIT = timedelta(hours=36)


def readiness() -> dict:
    checks, problems = {}, []
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            checks["database"] = "ok"
            now = utcnow()
            oldest = db.query(func.min(Job.run_at)).filter(Job.status == "queued", Job.run_at <= now).scalar()
            lag = (now - oldest) if oldest else timedelta(0)
            checks["queue_lag_seconds"] = int(lag.total_seconds())
            if lag > QUEUE_LAG_LIMIT:
                problems.append(f"jobs waiting {int(lag.total_seconds() // 60)} min - is the worker running?")
            last_done = db.query(func.max(Job.finished_at)).filter(Job.status == "done").scalar()
            checks["worker_last_job_seconds_ago"] = int((now - last_done).total_seconds()) if last_done else None
            if settings.app_env == "production" and (last_done is None or now - last_done > WORKER_SILENT_LIMIT):
                problems.append("the worker hasn't finished a job recently")
            last_backup = (
                db.query(func.max(Job.finished_at)).filter(Job.kind == "ops.backup_database", Job.status == "done").scalar()
            )
            checks["last_backup_hours_ago"] = round((now - last_backup).total_seconds() / 3600, 1) if last_backup else None
            if settings.app_env == "production" and (last_backup is None or now - last_backup > BACKUP_AGE_LIMIT):
                problems.append("no successful database backup in the last 36 hours")
            dead = db.query(Job).filter(Job.status == "dead").count()
            checks["dead_jobs"] = dead
    except Exception as exc:  # noqa: BLE001 - the report is the point
        checks["database"] = f"error: {type(exc).__name__}"
        problems.append("database unreachable")
    return {"status": "ok" if not problems else "degraded", "problems": problems, "checks": checks, "release": settings.git_sha or None}
