import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.database import get_db
from app.models.cms import CmsContent, CmsContentVersion
from app.models.user import User
from app.schemas.cms import CmsContentIn, CmsContentOut, CmsContentVersionOut

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


def _save(db: Session, key: str, content: dict, admin: User) -> CmsContent:
    """Every save is also appended to cms_content_versions, so the history
    holds each value that was ever live (newest = current)."""
    editor = admin.name or admin.username or admin.phone
    row = db.get(CmsContent, key)
    if row is None:
        row = CmsContent(key=key, content=content, updated_by=editor)
        db.add(row)
    else:
        row.content = content
        row.updated_by = editor
    db.add(CmsContentVersion(key=key, content=content, updated_by=editor))
    db.commit()
    db.refresh(row)
    return row


@router.put("/{key}", response_model=CmsContentOut)
def set_content(key: str, payload: CmsContentIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return _save(db, key, payload.content, admin)


@router.get("/{key}/versions", response_model=list[CmsContentVersionOut], dependencies=[Depends(require_role("admin"))])
def list_versions(key: str, db: Session = Depends(get_db)):
    return (
        db.query(CmsContentVersion)
        .filter(CmsContentVersion.key == key)
        .order_by(CmsContentVersion.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("/{key}/versions/{version_id}/restore", response_model=CmsContentOut)
def restore_version(
    key: str, version_id: uuid.UUID, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)
):
    version = db.get(CmsContentVersion, version_id)
    if version is None or version.key != key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    return _save(db, key, version.content, admin)
