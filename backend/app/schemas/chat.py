import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    sender_id: uuid.UUID
    sender_role: str
    body: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
