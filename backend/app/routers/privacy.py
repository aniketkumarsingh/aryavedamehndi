"""Your data: download a copy, or delete your account (app/services/privacy.py)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import privacy

router = APIRouter(prefix="/users/me", tags=["users"])


class DeleteIn(BaseModel):
    confirm: str = Field(description='Type "DELETE" to confirm')


class DeleteOut(BaseModel):
    status: str
    deleted_at: datetime


@router.get("/export")
def export_my_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = jsonable_encoder(privacy.export_data(db, user))
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="aryaveda-my-data.json"'})


@router.get("/deletion-check")
def deletion_check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reasons = privacy.open_items(db, user)
    return {"can_delete": not reasons and user.role != "admin", "blocking": reasons}


@router.post("/delete", response_model=DeleteOut)
def delete_my_account(payload: DeleteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.confirm.strip().upper() != "DELETE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Type DELETE to confirm')
    try:
        privacy.delete_account(db, user)
    except privacy.PrivacyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return DeleteOut(status="deleted", deleted_at=user.deleted_at)
