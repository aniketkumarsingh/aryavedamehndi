import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.database import Base

# queued -> running -> done
#                   -> queued again (retry with backoff) ... -> dead (gave up)
JOB_STATUSES = ("queued", "running", "done", "dead")


class Job(Base):
    """A unit of background work, run by `python -m app.worker`. Rows are
    claimed with SELECT ... FOR UPDATE SKIP LOCKED, so any number of workers
    can run side by side without picking up the same job."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_at", "status", "run_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    # Unique, so enqueueing the same logical job twice (a webhook delivered
    # twice, a scheduled task fired by two workers) creates one row.
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=True, unique=True)
    locked_by: Mapped[str] = mapped_column(String(80), nullable=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
