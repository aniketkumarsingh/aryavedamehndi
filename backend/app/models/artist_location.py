import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow

# An artist's profile carries one primary location (base_lat/base_lng).
# This table holds up to 2 additional service locations (e.g. "Mother's
# house", "Weekend spot") so nearby-artist search can match against any of
# them - up to 3 locations per artist in total.
MAX_EXTRA_LOCATIONS = 2


class ArtistLocation(Base):
    __tablename__ = "artist_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artist_profiles.user_id"), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    address_text: Mapped[str] = mapped_column(Text, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
