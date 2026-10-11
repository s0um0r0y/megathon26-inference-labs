"""POST /api/analyze (multipart: metadata JSON + image + optional audio), plus
/api/speak (TTS for on-demand text such as "Explain simpler") and /api/help."""

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from api.sessions import SessionStore, get_store
from orchestration import pipeline
from schemas.request import AnalyzeMetadata, HelpRequest, SpeakRequest
from schemas.response import AnalyzeResponse, HelpOffer, ProgressEvent, SpeakResponse, Stage, Status

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analyze"])

MAX_IMAGE_BYTES = 4 * 1024 * 1024  # the client sends one compressed frame (~200 KB)
MAX_AUDIO_BYTES = 3 * 1024 * 1024  # ~90 s of 16 kHz mono PCM
IMAGE_TYPES = {"image/jpeg"}
AUDIO_TYPES = {"audio/wav", "audio/x-wav", "audio/wave"}


def get_services(request: Request) -> pipeline.Services:
    return request.app.state.services


async def _read_limited(f: UploadFile, limit: int, label: str) -> bytes:
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"{label} too large")
    return data


@router.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
async def analyze(
    metadata: str = Form(...),
    image: UploadFile = File(...),
    audio: UploadFile | None = File(None),
    store: SessionStore = Depends(get_store),
    svc: pipeline.Services = Depends(get_services),
):
    try:
        meta = AnalyzeMetadata.model_validate_json(metadata)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False)) from e
    session = store.require(meta.session_id)
    if image.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "image must be image/jpeg")
    if audio is not None and audio.content_type not in AUDIO_TYPES:
        raise HTTPException(415, "audio must be 16 kHz mono WAV")
    if meta.request_id in session.active:
        raise HTTPException(409, "request_id already in flight")

    img = await _read_limited(image, MAX_IMAGE_BYTES, "image")
    wav = await _read_limited(audio, MAX_AUDIO_BYTES, "audio") if audio else None

    async def emit(stage: Stage, message: str) -> None:
        await store.broadcast(
            session.id, ProgressEvent(request_id=meta.request_id, stage=stage, message=message)
        )

    inp = pipeline.PipelineInput(
        meta=meta, image=img, audio_wav=wav, language=session.language, profile=session.profile
    )
    task = asyncio.create_task(pipeline.run(svc, inp, emit))
    session.active[meta.request_id] = task
    try:
        return await task
    except asyncio.CancelledError:
        # If *this* handler is being cancelled (client hung up), propagate.
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
        # Otherwise the user cancelled over the WebSocket.
        return AnalyzeResponse(
            request_id=meta.request_id, status=Status.cancelled, language=session.language
        )
    finally:
        session.active.pop(meta.request_id, None)


@router.post("/speak", response_model=SpeakResponse)
async def speak(
    body: SpeakRequest,
    store: SessionStore = Depends(get_store),
    svc: pipeline.Services = Depends(get_services),
):
    session = store.require(body.session_id)
    lang = body.language or session.language
    audio_b64 = mime = None
    if svc.bhashini.configured:
        try:
            async with asyncio.timeout(svc.settings.tts_timeout_s):
                audio_b64, mime = await svc.bhashini.tts(body.text, lang)
        except Exception as e:  # noqa: BLE001 - client falls back to on-device speech
            log.warning("speak failed: %r", e)
    return SpeakResponse(audio_b64=audio_b64, audio_mime=mime, text=body.text, language=lang)


@router.post("/help", response_model=HelpOffer)
async def request_help(
    body: HelpRequest,
    store: SessionStore = Depends(get_store),
    svc: pipeline.Services = Depends(get_services),
):
    session = store.require(body.session_id)
    _, offer = svc.helpdesk.submit(body, session.language)
    return offer


@router.get("/help/open")
async def open_help_tickets(svc: pipeline.Services = Depends(get_services)):
    """Volunteer view of pending help requests (demo only, unauthenticated)."""
    return [t.__dict__ for t in svc.helpdesk.open_tickets()]
