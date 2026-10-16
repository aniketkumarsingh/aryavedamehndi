import uuid
from datetime import datetime

from pydantic import BaseModel


class FavoriteArtistOut(BaseModel):
    artist_id: uuid.UUID
    name: str | None
    gender: str | None
    bio: str | None
    profile_photo_url: str | None
    rating_avg: float
    rating_count: int
    favorited_at: datetime
