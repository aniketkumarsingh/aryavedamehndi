import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow


class RefreshToken(Base):
    """One row per issued refresh token (keyed by its JWT `jti`), so
    refresh tokens rotate: each use revokes the old one and issues a new
    one. Presenting an already-revoked token means it was stolen and
    replayed, so every token for that user is revoked - see POST
    /auth/refresh."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
