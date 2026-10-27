"""Admin team (owner only), the audit log (owner only) and internal notes on
orders, bookings and bulk orders (every admin role)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.permissions import effective_role
from app.database import get_db
from app.models.admin_ops import AdminAuditLog, AdminNote
from app.models.booking import Booking
from app.models.bulk_order import BulkOrder
from app.models.shop import ShopOrder
from app.models.user import User
from app.services.auth_tokens import revoke_all_for_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])
NOTE_TARGETS = {"shop_order": ShopOrder, "booking": Booking, "bulk_order": BulkOrder, "user": User}


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    name: str | None
    phone: str
    admin_role: str
    is_active: bool


class TeamMemberIn(BaseModel):
    phone: str = Field(pattern=r"^\d{10}$")
    name: str = Field(min_length=2, max_length=120)
    admin_role: str = Field(pattern="^(owner|ops|support)$")


class TeamUpdateIn(BaseModel):
    admin_role: str | None = Field(default=None, pattern="^(owner|ops|support)$")
    is_active: bool | None = None


class AuditOut(BaseModel):
    id: uuid.UUID
    admin_id: uuid.UUID | None
    admin_name: str | None = None
    admin_role: str | None
    method: str
    path: str
    query: str | None
    status_code: int
    request_id: str | None
    ip: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class NoteIn(BaseModel):
    target_type: str = Field(pattern="^(shop_order|booking|bulk_order|user)$")
    target_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4000)


class NoteOut(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    author: str | None = None
    body: str
    created_at: datetime


def _member(user: User) -> TeamMemberOut:
    return TeamMemberOut(id=user.id, name=user.name, phone=user.phone, admin_role=effective_role(user.admin_role), is_active=user.is_active)


def _active_owners(db: Session) -> list[User]:
    return [u for u in db.query(User).filter(User.role == "admin", User.is_active.is_(True)) if effective_role(u.admin_role) == "owner"]


@router.get("/team", response_model=list[TeamMemberOut])
def list_team(db: Session = Depends(get_db)):
    return [_member(u) for u in db.query(User).filter(User.role == "admin").order_by(User.created_at)]


@router.post("/team", response_model=TeamMemberOut)
def add_member(payload: TeamMemberIn, db: Session = Depends(get_db)):
    """Adds an admin by phone (they sign in with an OTP like anyone else).
    An existing customer or artist account can't be turned into an admin."""
    user = db.query(User).filter(User.phone == payload.phone).first()
    if user is not None and user.role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That phone number belongs to a customer or artist account - use another number for admin work")
    if user is None:
        user = User(phone=payload.phone, name=payload.name, role="admin")
        db.add(user)
    user.admin_role, user.is_active = payload.admin_role, True
    db.commit()
    db.refresh(user)
    return _member(user)


@router.put("/team/{user_id}", response_model=TeamMemberOut)
def update_member(user_id: uuid.UUID, payload: TeamUpdateIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.role != "admin":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin not found")
    losing_owner = effective_role(user.admin_role) == "owner" and (
        (payload.admin_role and payload.admin_role != "owner") or payload.is_active is False)
    if losing_owner and len(_active_owners(db)) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Keep at least one active owner")
    if payload.admin_role:
        user.admin_role = payload.admin_role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            revoke_all_for_user(db, user.id)  # signs them out everywhere
    db.commit()
    db.refresh(user)
    return _member(user)


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    admin_id: uuid.UUID | None = None,
    path_contains: str | None = Query(None, max_length=100),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(AdminAuditLog)
    if admin_id:
        q = q.filter(AdminAuditLog.admin_id == admin_id)
    if path_contains:
        q = q.filter(AdminAuditLog.path.contains(path_contains))
    rows = q.order_by(AdminAuditLog.created_at.desc()).limit(limit).all()
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_({r.admin_id for r in rows if r.admin_id}))}
    out = []
    for r in rows:
        item = AuditOut.model_validate(r)
        item.admin_name = names.get(r.admin_id)
        out.append(item)
    return out


@router.get("/notes", response_model=list[NoteOut])
def list_notes(target_type: str = Query(..., pattern="^(shop_order|booking|bulk_order|user)$"), target_id: uuid.UUID = Query(...),
               db: Session = Depends(get_db)):
    rows = (db.query(AdminNote, User.name).join(User, User.id == AdminNote.author_id)
            .filter(AdminNote.target_type == target_type, AdminNote.target_id == target_id).order_by(AdminNote.created_at).all())
    return [NoteOut(id=n.id, target_type=n.target_type, target_id=n.target_id, author=name, body=n.body, created_at=n.created_at) for n, name in rows]


@router.post("/notes", response_model=NoteOut)
def add_note(payload: NoteIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if db.get(NOTE_TARGETS[payload.target_type], payload.target_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    note = AdminNote(id=uuid.uuid4(), target_type=payload.target_type, target_id=payload.target_id, author_id=admin.id, body=payload.body.strip())
    db.add(note)
    db.commit()
    return NoteOut(id=note.id, target_type=note.target_type, target_id=note.target_id, author=admin.name, body=note.body, created_at=note.created_at)

