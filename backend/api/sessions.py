"""Sessions: user language, condition profile, live WebSockets and in-flight requests.

In-memory for the hackathon (single backend process). If you ever run several
instances, move Session data to Redis and fan progress events out via pub/sub;
in-flight asyncio tasks can only be cancelled on the instance that owns them.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket

from schemas.request import Language, Profile, SessionCreate, SessionUpdate
from schemas.response import ProgressEvent, SessionOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@dataclass
class Session:
    id: str
    language: Language
    profile: Profile
    speech_rate: float
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    active: dict[str, asyncio.Task] = field(default_factory=dict)
    sockets: set[WebSocket] = field(default_factory=set)

    def out(self) -> SessionOut:
        return SessionOut(
            session_id=self.id, language=self.language, profile=self.profile,
            speech_rate=self.speech_rate,
        )


class SessionStore:
    def __init__(self, ttl_s: int):
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_s

    def create(self, body: SessionCreate) -> Session:
        s = Session(uuid.uuid4().hex, body.language, body.profile, body.speech_rate)
        self._sessions[s.id] = s
        return s

    def get(self, session_id: str) -> Session | None:
        s = self._sessions.get(session_id)
        if s:
            s.last_seen = time.time()
        return s

    def require(self, session_id: str) -> Session:
        s = self.get(session_id)
        if s is None:
            raise HTTPException(404, "Unknown or expired session; create a new one.")
        return s

    def cancel(self, session_id: str, request_id: str) -> bool:
        s = self._sessions.get(session_id)
        task = s.active.get(request_id) if s else None
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def broadcast(self, session_id: str, event: ProgressEvent) -> None:
        s = self._sessions.get(session_id)
        if not s:
            return
        payload = event.model_dump(mode="json")
        for ws in list(s.sockets):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - socket went away mid-send
                s.sockets.discard(ws)

    async def purge_forever(self, every_s: float = 60) -> None:
        while True:
            await asyncio.sleep(every_s)
            cutoff = time.time() - self._ttl
            for sid in [k for k, s in self._sessions.items() if s.last_seen < cutoff and not s.sockets]:
                for task in self._sessions[sid].active.values():
                    task.cancel()
                del self._sessions[sid]


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate, store: SessionStore = Depends(get_store)):
    return store.create(body).out()


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, store: SessionStore = Depends(get_store)):
    return store.require(session_id).out()


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str, body: SessionUpdate, store: SessionStore = Depends(get_store)
):
    s = store.require(session_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    return s.out()
