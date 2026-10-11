"""WS /ws/{session_id}: server pushes ProgressEvents for the session's requests;
client sends {"type": "cancel", "request_id": ...} or {"type": "ping"}."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from schemas.request import ClientWsMessage

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/{session_id}")
async def session_socket(ws: WebSocket, session_id: str):
    store = ws.app.state.store
    session = store.get(session_id)
    if session is None:
        await ws.close(code=4404, reason="unknown session")
        return
    await ws.accept()
    session.sockets.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = ClientWsMessage.model_validate_json(raw)
            except ValidationError:
                await ws.send_json({"type": "error", "message": "bad message"})
                continue
            if msg.type == "ping":
                store.get(session_id)  # keeps the session alive
                await ws.send_json({"type": "pong"})
            elif msg.type == "cancel" and msg.request_id:
                cancelled = store.cancel(session_id, msg.request_id)
                await ws.send_json(
                    {"type": "cancel_ack", "request_id": msg.request_id, "cancelled": cancelled}
                )
    except WebSocketDisconnect:
        pass
    finally:
        session.sockets.discard(ws)
