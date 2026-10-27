"""Shipping endpoints: PIN-code serviceability (public), courier webhooks,
and the admin dispatch tools - book one or many orders, edit courier
details, log tracking by hand, print labels and the pickup manifest."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.shipping import Shipment
from app.models.shop import ShopOrder, ShopOrderItem
from app.models.user import User
from app.services.shipping import ShippingError, WebhookNotSupported
from app.services.shipping.labels import labels_pdf, manifest_pdf
from app.services.shipping.service import (
    active_shipment,
    book_shipment,
    receive_return,
    record_cod_remittance,
    respond_to_ndr,
    shipping_report,
    unremitted_cod,
    check_serviceability,
    delivery_window,
    record_manual_update,
    record_webhook,
    update_details,
    valid_pincode,
)

router = APIRouter(tags=["shipping"])
admin_router = APIRouter(prefix="/admin/shipping", tags=["admin"], dependencies=[Depends(require_role("admin"))])


class ServiceabilityOut(BaseModel):
    pincode: str
    deliverable: bool
    cod_available: bool
    eta_min_days: int | None
    eta_max_days: int | None
    estimated_delivery: tuple[str, str] | None  # ("29 Oct", "2 Nov")


class ShipIn(BaseModel):
    courier_name: str | None = Field(default=None, max_length=80)
    awb: str | None = Field(default=None, max_length=80)
    tracking_url: str | None = Field(default=None, max_length=300)
    shipping_charge: float | None = Field(default=None, ge=0, le=100_000)  # what the courier billed us


class NdrResponseIn(BaseModel):
    action: Literal["reattempt", "change_address", "cancel"]
    address: str | None = Field(default=None, max_length=2000)
    pincode: str | None = Field(default=None, max_length=6)
    phone: str | None = Field(default=None, max_length=15)
    preferred_date: str | None = Field(default=None, max_length=20)


class ReceiveReturnIn(BaseModel):
    condition: Literal["good", "damaged"]
    note: str | None = Field(default=None, max_length=200)


class RemittanceIn(BaseModel):
    shipment_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    reference: str = Field(min_length=3, max_length=80)  # bank UTR / courier batch id
    remitted_on: datetime | None = None


class BulkShipIn(BaseModel):
    order_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    courier_name: str | None = Field(default=None, max_length=80)


class BulkResultOut(BaseModel):
    order_id: uuid.UUID
    shipment_id: uuid.UUID | None = None
    error: str | None = None


class ShipmentUpdateIn(BaseModel):
    status: Literal["picked_up", "in_transit", "out_for_delivery", "delivered", "ndr", "rto", "rto_delivered"]
    description: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=120)


class AdminShipmentOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    awb: str | None
    courier_name: str | None
    tracking_url: str | None
    label_url: str | None
    status: str
    weight_g: int
    cod_amount: float
    shipping_charge: float | None
    created_at: datetime
    last_event_at: datetime | None
    delivered_at: datetime | None
    cod_remitted_at: datetime | None = None
    cod_remittance_ref: str | None = None
    ndr_status: str | None = None
    ndr_action: str | None = None
    ndr_attempts: int = 0
    ndr_note: str | None = None
    ndr_raised_at: datetime | None = None
    customer: str | None = None
    pincode: str | None = None

    class Config:
        from_attributes = True


@router.get("/shop/serviceability", response_model=ServiceabilityOut)
def serviceability(pincode: str = Query(min_length=6, max_length=6), db: Session = Depends(get_db)):
    """Can we deliver here, with Cash on Delivery, and roughly when?"""
    if not valid_pincode(pincode):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a valid 6-digit PIN code")
    answer = check_serviceability(db, pincode)
    db.commit()  # keeps the cache entry
    return ServiceabilityOut(pincode=pincode, deliverable=answer.deliverable, cod_available=answer.cod_available,
                             eta_min_days=answer.eta_min_days, eta_max_days=answer.eta_max_days,
                             estimated_delivery=delivery_window(answer) if answer.deliverable else None)


@router.post("/shipping/webhook/{provider}")
async def courier_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    try:
        outcome = record_webhook(db, provider, dict(request.headers), body)
    except (ShippingError, WebhookNotSupported):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No webhook for this provider")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook")
    db.commit()
    return {"status": outcome}


# ------------------------------------------------------------------ admin --

def _order_or_404(db: Session, order_id) -> ShopOrder:
    order = db.get(ShopOrder, order_id, with_for_update=True)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _out(db: Session, shipment: Shipment) -> AdminShipmentOut:
    order = db.get(ShopOrder, shipment.order_id)
    out = AdminShipmentOut.model_validate(shipment)
    out.customer, out.pincode = order.shipping_name, order.shipping_pincode
    return out


@admin_router.post("/orders/{order_id}/shipments", response_model=AdminShipmentOut)
def ship_order(order_id: uuid.UUID, payload: ShipIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = _order_or_404(db, order_id)
    try:
        shipment = book_shipment(db, order, payload.model_dump(), created_by=admin.id)
    except ShippingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _out(db, shipment)


@admin_router.post("/bulk-book", response_model=list[BulkResultOut])
def bulk_book(payload: BulkShipIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Books many confirmed orders in one go (the daily packing run). Each
    order succeeds or fails on its own; AWBs can be added afterwards."""
    results = []
    for order_id in dict.fromkeys(payload.order_ids):
        order = db.get(ShopOrder, order_id, with_for_update=True)
        if order is None:
            results.append(BulkResultOut(order_id=order_id, error="Order not found"))
            continue
        try:
            with db.begin_nested():
                shipment = book_shipment(db, order, {"courier_name": payload.courier_name}, created_by=admin.id)
            results.append(BulkResultOut(order_id=order_id, shipment_id=shipment.id))
        except ShippingError as exc:
            results.append(BulkResultOut(order_id=order_id, error=str(exc)))
    db.commit()
    return results


@admin_router.get("/shipments", response_model=list[AdminShipmentOut])
def list_shipments(status_filter: str = "active", limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = db.query(Shipment).order_by(Shipment.created_at.desc())
    if status_filter == "active":
        query = query.filter(Shipment.status.notin_(("delivered", "rto_delivered", "cancelled")))
    elif status_filter != "all":
        query = query.filter(Shipment.status == status_filter)
    return [_out(db, s) for s in query.limit(limit).all()]


@admin_router.put("/shipments/{shipment_id}", response_model=AdminShipmentOut)
def edit_shipment(shipment_id: uuid.UUID, payload: ShipIn, db: Session = Depends(get_db)):
    shipment = db.get(Shipment, shipment_id, with_for_update=True)
    if shipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    if payload.tracking_url and not payload.tracking_url.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The tracking link must start with http:// or https://")
    update_details(db, shipment, payload.courier_name, payload.awb, payload.tracking_url, payload.shipping_charge)
    db.commit()
    return _out(db, shipment)


@admin_router.post("/shipments/{shipment_id}/events", response_model=AdminShipmentOut)
def add_tracking_update(shipment_id: uuid.UUID, payload: ShipmentUpdateIn, db: Session = Depends(get_db)):
    """Tracking by hand (manual provider), e.g. "out for delivery"."""
    shipment = db.get(Shipment, shipment_id, with_for_update=True)
    if shipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    record_manual_update(db, shipment, payload.status, payload.description, payload.location)
    db.commit()
    return _out(db, shipment)


def _rows(db: Session, ids: str) -> list:
    try:
        wanted = [uuid.UUID(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad shipment id")
    if not wanted or len(wanted) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose 1-200 shipments")
    rows = []
    for shipment in db.query(Shipment).filter(Shipment.id.in_(wanted)).order_by(Shipment.created_at).all():
        order = db.get(ShopOrder, shipment.order_id)
        items = sum(i.quantity for i in db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id))
        rows.append((shipment, order, items))
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shipments")
    return rows


@admin_router.get("/labels.pdf")
def labels(ids: str, db: Session = Depends(get_db)):
    return Response(labels_pdf(_rows(db, ids)), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="labels.pdf"'})


@admin_router.get("/manifest.pdf")
def manifest(ids: str, db: Session = Depends(get_db)):
    return Response(manifest_pdf(_rows(db, ids)), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="manifest.pdf"'})


# ------------------------------------------------- failed deliveries & money --

@router.post("/shop/orders/{order_id}/delivery-issue")
def answer_failed_delivery(order_id: uuid.UUID, payload: NdrResponseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The customer's answer to a failed delivery attempt."""
    order = db.get(ShopOrder, order_id, with_for_update=True)
    if order is None or order.consumer_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    shipment = active_shipment(db, order.id)
    if shipment is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This order hasn't shipped")
    try:
        respond_to_ndr(db, shipment, payload.action, payload.model_dump(), by="customer")
    except ShippingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return {"status": "ok", "action": payload.action}


@admin_router.post("/shipments/{shipment_id}/ndr-action", response_model=AdminShipmentOut)
def admin_ndr_action(shipment_id: uuid.UUID, payload: NdrResponseIn, db: Session = Depends(get_db)):
    shipment = db.get(Shipment, shipment_id, with_for_update=True)
    if shipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    try:
        respond_to_ndr(db, shipment, payload.action, payload.model_dump(), by="admin")
    except ShippingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _out(db, shipment)


@admin_router.post("/shipments/{shipment_id}/receive-return", response_model=AdminShipmentOut)
def admin_receive_return(shipment_id: uuid.UUID, payload: ReceiveReturnIn, admin: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A returned parcel is back: confirm its condition (restock if good) -
    prepaid orders are refunded with a credit note."""
    shipment = db.get(Shipment, shipment_id, with_for_update=True)
    if shipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shipment not found")
    db.get(ShopOrder, shipment.order_id, with_for_update=True)
    try:
        receive_return(db, shipment, payload.condition, payload.note, admin.id)
    except ShippingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return _out(db, shipment)


@admin_router.post("/cod-remittances")
def add_cod_remittance(payload: RemittanceIn, db: Session = Depends(get_db)):
    """Records a courier COD payout (from their remittance statement)."""
    shipments = db.query(Shipment).filter(Shipment.id.in_(payload.shipment_ids)).with_for_update().all()
    if len(shipments) != len(set(payload.shipment_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some shipments weren't found")
    try:
        changed = record_cod_remittance(db, shipments, payload.reference, payload.remitted_on)
    except ShippingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return {"recorded": changed, "total": round(sum(s.cod_amount for s in shipments if s.cod_remittance_ref == payload.reference[:80]), 2)}


@admin_router.get("/cod-unremitted", response_model=list[AdminShipmentOut])
def cod_unremitted(older_than_days: int = Query(0, ge=0, le=365), db: Session = Depends(get_db)):
    """Delivered COD parcels the courier hasn't paid over yet."""
    return [_out(db, s) for s in unremitted_cod(db, older_than_days)]


@admin_router.get("/report")
def report(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """Monthly shipping cost vs. what customers paid for delivery."""
    return shipping_report(db, months)
