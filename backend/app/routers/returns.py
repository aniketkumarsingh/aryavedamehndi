"""Return requests: customers ask (with photos), admins approve (booking the
reverse pickup), reject, and confirm receipt - which restocks and refunds.
See app/services/returns.py for the rules."""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.shop import ReturnRequest, ShopOrder
from app.models.user import User
from app.services import returns as returns_service
from app.services.returns import ReturnError
from app.services.storage import save_upload

router = APIRouter(tags=["returns"])
admin_router = APIRouter(prefix="/admin/returns", tags=["admin"], dependencies=[Depends(require_role("admin"))])

MAX_PHOTOS = 3


class ReturnRequestOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    status: str
    reason_code: str
    details: str | None
    photo_urls: str | None
    items: list
    refund_amount: float
    refund_upi: str | None
    condition: str | None
    admin_note: str | None
    created_at: datetime
    decided_at: datetime | None
    received_at: datetime | None

    class Config:
        from_attributes = True


class AdminReturnOut(ReturnRequestOut):
    customer: str | None = None
    payment_method: str | None = None


class ApproveIn(BaseModel):
    courier_name: str | None = Field(default=None, max_length=80)
    awb: str | None = Field(default=None, max_length=80)
    tracking_url: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=300)


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=300)


class ReceiveIn(BaseModel):
    condition: str = Field(pattern="^(good|damaged)$")
    upi_reference: str | None = Field(default=None, max_length=100)  # COD: UTR of the UPI refund


@router.post("/shop/orders/{order_id}/returns", response_model=ReturnRequestOut)
async def request_return(
    order_id: uuid.UUID,
    items: str = Form(..., description='JSON: [{"order_item_id": "...", "quantity": 1}]'),
    reason_code: str = Form(...),
    details: str | None = Form(default=None),
    refund_upi: str | None = Form(default=None),
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(ShopOrder, order_id, with_for_update=True)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    try:
        lines = json.loads(items)
        assert isinstance(lines, list)
    except (ValueError, AssertionError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "items must be a JSON list")
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Add up to {MAX_PHOTOS} photos")
    urls = []
    for photo in photos:
        try:
            urls.append(save_upload(await photo.read(), "returns"))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Photo not accepted: {exc}")
    try:
        request = returns_service.create_request(db, order, user.id, lines, reason_code, details, urls, refund_upi)
    except ReturnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    db.refresh(request)
    return request


def _admin_out(db: Session, request: ReturnRequest) -> AdminReturnOut:
    order = db.get(ShopOrder, request.order_id)
    out = AdminReturnOut.model_validate(request)
    out.customer, out.payment_method = order.shipping_name, order.payment_method
    return out


def _request_or_404(db: Session, request_id) -> ReturnRequest:
    request = db.get(ReturnRequest, request_id, with_for_update=True)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Return not found")
    return request


@admin_router.get("", response_model=list[AdminReturnOut])
def list_returns(status_filter: str = "open", limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = db.query(ReturnRequest).order_by(ReturnRequest.created_at.desc())
    if status_filter == "open":
        query = query.filter(ReturnRequest.status.in_(("requested", "approved", "received")))
    elif status_filter != "all":
        query = query.filter(ReturnRequest.status == status_filter)
    return [_admin_out(db, r) for r in query.limit(limit).all()]


@admin_router.post("/{request_id}/approve", response_model=AdminReturnOut)
def approve_return(request_id: uuid.UUID, payload: ApproveIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request = _request_or_404(db, request_id)
    try:
        returns_service.approve(db, request, admin.id, payload.model_dump())
    except ReturnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _admin_out(db, request)


@admin_router.post("/{request_id}/reject", response_model=AdminReturnOut)
def reject_return(request_id: uuid.UUID, payload: RejectIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request = _request_or_404(db, request_id)
    try:
        returns_service.reject(db, request, admin.id, payload.note)
    except ReturnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _admin_out(db, request)


@admin_router.post("/{request_id}/receive", response_model=AdminReturnOut)
def receive_return_items(request_id: uuid.UUID, payload: ReceiveIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request = _request_or_404(db, request_id)
    db.get(ShopOrder, request.order_id, with_for_update=True)
    try:
        returns_service.receive(db, request, payload.condition, admin.id, payload.upi_reference)
    except ReturnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _admin_out(db, request)
