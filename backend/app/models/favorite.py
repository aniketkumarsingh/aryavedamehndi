import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("consumer_id", "artist_id", name="uq_favorite_consumer_artist"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artist_profiles.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
