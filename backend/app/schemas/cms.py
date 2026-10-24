import uuid
from datetime import datetime

from pydantic import BaseModel


class CmsContentIn(BaseModel):
    content: dict


class CmsContentVersionOut(BaseModel):
    id: uuid.UUID
    key: str
    content: dict
    updated_by: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class CmsContentOut(BaseModel):
    key: str
    content: dict
    updated_by: str | None
    updated_at: datetime

    class Config:
        from_attributes = True
