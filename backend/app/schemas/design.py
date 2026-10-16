import uuid
from datetime import datetime

from pydantic import BaseModel


class DesignUploadOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    completed_image_url: str
    reference_image_url: str | None
    similarity_score: float | None
    match_status: str
    uploaded_at: datetime
    confirmed_at: datetime | None

    class Config:
        from_attributes = True


class ConsumerConfirmIn(BaseModel):
    # true = "I'm satisfied, release payment anyway"
    satisfied: bool
