import uuid

from fastapi import WebSocket


class ChatConnectionManager:
    """In-memory per-booking WebSocket registry.

    Single-process only - fine for one uvicorn worker in dev. Scaling to
    multiple workers/instances would need a shared pub/sub (e.g. Redis)
    to fan out messages across processes.
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, dict[WebSocket, uuid.UUID]] = {}

    async def connect(self, booking_id: uuid.UUID, websocket: WebSocket, user_id: uuid.UUID) -> None:
        await websocket.accept()
        self._connections.setdefault(booking_id, {})[websocket] = user_id

    def disconnect(self, booking_id: uuid.UUID, websocket: WebSocket) -> None:
        conns = self._connections.get(booking_id)
        if not conns:
            return
        conns.pop(websocket, None)
        if not conns:
            self._connections.pop(booking_id, None)

    def other_party_connected(self, booking_id: uuid.UUID, sender_id: uuid.UUID) -> bool:
        conns = self._connections.get(booking_id, {})
        return any(uid != sender_id for uid in conns.values())

    async def broadcast(self, booking_id: uuid.UUID, message: dict) -> None:
        for ws in list(self._connections.get(booking_id, {}).keys()):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(booking_id, ws)


chat_manager = ChatConnectionManager()
