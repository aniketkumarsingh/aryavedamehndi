from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow


class PlatformSetting(Base):
    """Admin-tunable business settings (platform fee, design-match
    threshold, strike limit, check-in distance) - one row per key, so they
    can change from the admin panel without a redeploy. Missing keys fall
    back to the .env defaults - see app/services/platform_settings.py."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
