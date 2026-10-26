"""Admin payment operations: the health summary, refunds, the gateway
event log, reconciliation runs and the background job queue."""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.time import utcnow
from app.database import get_db
from app.models.job import Job
from app.models.payment_ops import PaymentEvent, ReconciliationRun, Refund
from app.schemas.shop import AdminRefundOut
from app.services.jobs import enqueue, retry_job
from app.services.refunds import RefundError, retry_refund

router = APIRouter(prefix="/admin/payments", tags=["admin"], dependencies=[Depends(require_role("admin"))])


class EventOut(BaseModel):
    id: uuid.UUID
    event_id: str
    event_type: str
    status: str
    result: str | None
    error: str | None
    received_at: datetime
    processed_at: datetime | None

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: uuid.UUID
    window_from: datetime
    window_to: datetime
    status: str
    payments_seen: int
    fixed: int
    issues: list
    note: str | None
    started_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    run_at: datetime
    created_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True


class SummaryOut(BaseModel):
    jobs_by_status: dict[str, int]
    oldest_queued_seconds: int | None  # queue lag; high means no worker is running
    dead_jobs: int
    refunds_failed: int
    refunds_in_flight: int
    events_unprocessed: int
    last_reconciliation: RunOut | None
    alerts: list[str]


@router.get("/summary", response_model=SummaryOut)
def summary(db: Session = Depends(get_db)):
    jobs = dict(db.query(Job.status, func.count()).group_by(Job.status).all())
    oldest = db.query(func.min(Job.run_at)).filter(Job.status == "queued", Job.run_at <= utcnow()).scalar()
    lag = int((utcnow() - oldest).total_seconds()) if oldest else None
    refunds_failed = db.query(Refund).filter(Refund.status == "failed").count()
    in_flight = db.query(Refund).filter(Refund.status.in_(("pending", "submitted"))).count()
    unprocessed = db.query(PaymentEvent).filter(PaymentEvent.status == "received").count()
    last = db.query(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).first()

    alerts = []
    if lag is not None and lag > 300:
        alerts.append(f"Jobs have been waiting {lag // 60} min - is the worker (python -m app.worker) running?")
    if jobs.get("dead"):
        alerts.append(f"{jobs['dead']} background job(s) gave up - review and retry below.")
    if refunds_failed:
        alerts.append(f"{refunds_failed} refund(s) failed and need attention.")
    if last and last.status == "issues":
        alerts.append(f"The last reconciliation found {len(last.issues)} issue(s).")
    last_backup = db.query(func.max(Job.finished_at)).filter(Job.kind == "ops.backup_database", Job.status == "done").scalar()
    if last_backup is None or utcnow() - last_backup > timedelta(hours=36):
        alerts.append("No database backup in the last 36 hours - check the worker and backup storage.")
    return SummaryOut(
        jobs_by_status=jobs,
        oldest_queued_seconds=lag,
        dead_jobs=jobs.get("dead", 0),
        refunds_failed=refunds_failed,
        refunds_in_flight=in_flight,
        events_unprocessed=unprocessed,
        last_reconciliation=RunOut.model_validate(last) if last else None,
        alerts=alerts,
    )


@router.get("/refunds", response_model=list[AdminRefundOut])
def list_refunds(
    status_filter: str = "all",
    target_type: str = "all",
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Refund).order_by(Refund.created_at.desc())
    if status_filter != "all":
        query = query.filter(Refund.status == status_filter)
    if target_type != "all":
        query = query.filter(Refund.target_type == target_type)
    return query.limit(limit).all()


@router.post("/refunds/{refund_id}/retry", response_model=AdminRefundOut)
def retry_failed_refund(refund_id: uuid.UUID, db: Session = Depends(get_db)):
    refund = db.get(Refund, refund_id, with_for_update=True)
    if refund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Refund not found")
    try:
        retry_refund(db, refund)
    except RefundError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(refund)
    return refund


@router.get("/events", response_model=list[EventOut])
def list_events(status_filter: str = "all", limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    query = db.query(PaymentEvent).order_by(PaymentEvent.received_at.desc())
    if status_filter != "all":
        query = query.filter(PaymentEvent.status == status_filter)
    return query.limit(limit).all()


@router.post("/events/{event_id}/reprocess", response_model=EventOut)
def reprocess_event(event_id: uuid.UUID, db: Session = Depends(get_db)):
    """Runs a stored event through processing again (it's idempotent)."""
    event = db.get(PaymentEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    event.status, event.error = "received", None
    enqueue(db, "payments.process_event", {"event_row_id": str(event.id)}, dedupe_key=f"event-reprocess:{event.id}:{utcnow().timestamp():.0f}")
    db.commit()
    db.refresh(event)
    return event


@router.get("/reconciliation", response_model=list[RunOut])
def list_runs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).limit(limit).all()


@router.post("/reconciliation/run", status_code=202)
def run_reconciliation(db: Session = Depends(get_db)):
    enqueue(db, "payments.reconcile", {"manual": True}, dedupe_key=f"reconcile-manual:{utcnow():%Y%m%d%H%M}", max_attempts=3)
    db.commit()
    return {"status": "queued"}


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(status_filter: str = "dead", limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    query = db.query(Job).order_by(Job.created_at.desc())
    if status_filter != "all":
        query = query.filter(Job.status == status_filter)
    return query.limit(limit).all()


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_dead_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id, with_for_update=True)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.status != "dead":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a job that gave up can be retried")
    retry_job(db, job)
    db.commit()
    db.refresh(job)
    return job
