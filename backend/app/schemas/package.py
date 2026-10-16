import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PackageIn(BaseModel):
    name: str
    package_type: str = "regular"
    description: str | None = None
    price_min: float
    price_max: float
    duration_minutes: int = 60
    negotiable: bool = True
    sample_image_urls: str | None = None
    # Non-refundable-after-dispatch booking deposit for this package - 0
    # means none is required. See Booking.advance_amount/advance_status.
    advance_amount: float = Field(ge=0, le=100_000, default=0)


class PackageOut(PackageIn):
    id: uuid.UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
