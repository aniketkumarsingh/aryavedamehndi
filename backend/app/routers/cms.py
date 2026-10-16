from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.cms import CmsContent
from app.schemas.cms import CmsContentIn, CmsContentOut

router = APIRouter(prefix="/cms", tags=["cms"])


@router.get("/{key}", response_model=CmsContentOut)
def get_content(key: str, db: Session = Depends(get_db)):
    row = db.get(CmsContent, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No content set for this key yet")
    return row


@router.get("", response_model=list[CmsContentOut])
def list_content(db: Session = Depends(get_db)):
    return db.query(CmsContent).all()


@router.put("/{key}", response_model=CmsContentOut, dependencies=[Depends(require_role("admin"))])
def set_content(key: str, payload: CmsContentIn, db: Session = Depends(get_db)):
    row = db.get(CmsContent, key)
    if row is None:
        row = CmsContent(key=key, content=payload.content)
        db.add(row)
    else:
        row.content = payload.content
    db.commit()
    db.refresh(row)
    return row
