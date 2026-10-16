import uuid
from datetime import date, time

from pydantic import BaseModel


class AvailabilityIn(BaseModel):
    slot_date: date
    start_time: time
    end_time: time


class AvailabilityOut(AvailabilityIn):
    id: uuid.UUID
    artist_id: uuid.UUID
    status: str

    class Config:
        from_attributes = True
