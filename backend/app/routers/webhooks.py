"""Razorpay webhook endpoint. Verifies the signature, stores the event and
queues it for the worker (see app/services/payment_events.py), then
answers 200 straight away - Razorpay expects a reply within seconds and
retries anything else.

Set up in Razorpay Dashboard -> Settings -> Webhooks:
  URL     <PUBLIC_API_URL>/payments/razorpay/webhook
  Events  payment.captured, order.paid, refund.processed, refund.failed
  Secret  the same value as RAZORPAY_WEBHOOK_SECRET
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.payment_events import record_event
from app.services.razorpay_client import verify_webhook_signature

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_webhook_signature(body, request.headers.get("X-Razorpay-Signature")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")
    try:
        event_id, outcome = record_event(db, body, request.headers.get("X-Razorpay-Event-Id"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed webhook body")
    db.commit()
    return {"status": outcome, "event_id": event_id}
