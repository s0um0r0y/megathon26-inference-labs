"""SignSaathi backend entry point. Run from backend/: `uv run uvicorn main:app --reload`.

Also serves the PWA in ../frontend at /, so the phone uses one origin for the app
and the API (no CORS, and one HTTPS certificate covers camera, mic and API).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import analyze, ask, sessions, websocket
from api.sessions import SessionStore
from config import get_settings
from orchestration.pipeline import Services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=5.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    ) as http:
        app.state.services = Services.create(settings, http)
        app.state.store = SessionStore(settings.session_ttl_s)
        purger = asyncio.create_task(app.state.store.purge_forever())
        try:
            yield
        finally:
            purger.cancel()


app = FastAPI(title="SignSaathi", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sessions.router)
app.include_router(analyze.router)
app.include_router(websocket.router)
app.include_router(ask.router)


@app.get("/api/health")
async def health():
    svc: Services = app.state.services
    return {
        "ok": True,
        "language_provider": svc.settings.language_provider,
        "language": svc.bhashini.services() if svc.bhashini.configured else False,
        "vision": svc.vision.label if svc.vision.configured else False,
        "ocr": svc.ocr.provider,
    }


# Mounted last: API routes above take precedence over static files.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
