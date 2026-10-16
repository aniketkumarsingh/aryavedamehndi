import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import decode_token
from app.database import get_db
from app.models.booking import Booking
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatMessageOut
from app.services.chat_manager import chat_manager
from app.services.notifications import notify

router = APIRouter(tags=["chat"])


def _require_participant(db: Session, booking_id: uuid.UUID, user: User) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.consumer_id != user.id and booking.artist_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not part of this booking")
    return booking


@router.get("/bookings/{booking_id}/chat/messages", response_model=list[ChatMessageOut])
def list_chat_messages(
    booking_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_participant(db, booking_id, user)
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.booking_id == booking_id)
        .order_by(ChatMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


async def _authenticate_ws(websocket: WebSocket, db: Session) -> User | None:
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        return None
    return user


@router.websocket("/ws/bookings/{booking_id}/chat")
async def chat_websocket(websocket: WebSocket, booking_id: uuid.UUID, db: Session = Depends(get_db)):
    user = await _authenticate_ws(websocket, db)
    if user is None:
        await websocket.close(code=4401)
        return

    booking = db.get(Booking, booking_id)
    if booking is None or (booking.consumer_id != user.id and booking.artist_id != user.id):
        await websocket.close(code=4403)
        return

    await chat_manager.connect(booking_id, websocket, user.id)
    try:
        while True:
            data = await websocket.receive_json()
            body = (data.get("body") or "").strip()
            if not body or len(body) > 2000:
                continue

            message = ChatMessage(booking_id=booking_id, sender_id=user.id, sender_role=user.role, body=body)
            db.add(message)
            db.commit()
            db.refresh(message)

            out = {
                "id": str(message.id),
                "booking_id": str(booking_id),
                "sender_id": str(user.id),
                "sender_role": user.role,
                "body": body,
                "created_at": message.created_at.isoformat(),
            }
            await chat_manager.broadcast(booking_id, out)

            if not chat_manager.other_party_connected(booking_id, user.id):
                recipient_id = booking.artist_id if user.id == booking.consumer_id else booking.consumer_id
                notify(db, recipient_id, "chat", "New message", body[:100], f"/booking-detail/{booking_id}")
                db.commit()
    except WebSocketDisconnect:
        chat_manager.disconnect(booking_id, websocket)
