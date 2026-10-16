import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class ReviewOut(ReviewIn):
    id: uuid.UUID
    booking_id: uuid.UUID
    by_role: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportIn(BaseModel):
    category: str
    description: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    reported_by: uuid.UUID
    category: str
    description: str | None
    status: str
    resolution_notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ReportResolveIn(BaseModel):
    status: str  # "resolved" | "dismissed"
    resolution_notes: str | None = None
    strike_artist: bool = False
