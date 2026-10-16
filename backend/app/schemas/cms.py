from datetime import datetime

from pydantic import BaseModel


class CmsContentIn(BaseModel):
    content: dict


class CmsContentOut(BaseModel):
    key: str
    content: dict
    updated_by: str | None
    updated_at: datetime

    class Config:
        from_attributes = True
