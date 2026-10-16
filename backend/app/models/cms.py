import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CmsContent(Base):
    """Admin-editable content blocks the frontend renders directly.

    `key` is a stable slug the frontend requests by, e.g. "home.hero",
    "brand.story", "faq.list". `content` is arbitrary JSON so one table
    covers banners, copy blocks and structured lists without a schema
    change per content type.
    """

    __tablename__ = "cms_content"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
