from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RateLimitCounter(Base):
    """Fixed-window request counters for app/services/rate_limit.py. One
    row per key per window; old windows are deleted by a periodic job."""

    __tablename__ = "rate_limit_counters"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)  # e.g. "otp_request:ip:203.0.113.9"
    window_start: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
