"""Endpoints for the static PWA in frontend/ (its contract: frontend/README.md).

POST /api/ask  multipart: image, query, lang, profile (+ optional lat, lon, heading)
POST /api/tts  multipart: text, lang -> Bhashini audio for any text the app speaks

/api/ask runs the same pipeline as /api/analyze, statelessly (no session or
WebSocket), and maps the result onto the frontend's flat JSON. Safety cautions are
folded into `answer` and `simple`, because those are the strings the app speaks.
"""

import asyncio
import io
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from api.analyze import MAX_IMAGE_BYTES, _read_limited, get_services
from orchestration import pipeline
from schemas.request import AnalyzeMetadata, Language, Location, Profile
from schemas.response import AnalyzeResponse, Status

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pwa"])

UPLOAD_MAX_SIDE = 1600


def _as_jpeg(data: bytes) -> bytes:
    """Uploads may be PNG/WebP/HEIC-converted; the vision APIs are sent image/jpeg."""
    if data[:3] == b"\xff\xd8\xff":
        return data
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        im.thumbnail((UPLOAD_MAX_SIDE, UPLOAD_MAX_SIDE))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(415, "image must be a JPEG, PNG or WebP photo") from e


def _join(*parts: str | None) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def to_pwa(r: AnalyzeResponse, profile: Profile) -> dict:
    """Map a pipeline result onto the frontend's {answer, simple, more, ...} shape."""
    a = r.answer
    base = {
        "lang": r.language.value,  # language actually delivered (en if NMT was unavailable)
        "read_text": r.sign_text or "",
        "confidence": r.confidence.level.value if r.confidence else "medium",
        "intent": r.intent.value if r.intent else None,
        "raw_answer": r.raw_answer,
        "landmarks": [lm.model_dump() for lm in r.landmarks],
        "timings_ms": r.timings_ms,
    }
    if r.status in (Status.needs_retake, Status.needs_confirmation):
        hint = r.spoken_text or (r.retake_hint or "")
        return {**base, "needs_retake": True, "retake_hint": hint, "answer": hint, "simple": hint, "more": ""}
    caution = a.caution if a else None
    short = a.short if a else r.spoken_text
    return {
        **base,
        "needs_retake": False,
        "retake_hint": "",
        "answer": _join(short, caution),
        "simple": _join((a.simpler if a else None) or short, caution),
        "more": _join(*(a.steps if a else []), *(a.details if a else []), a.follow_up if a else None),
        "caution": caution,
        "steps": a.steps if a else [],
    }


async def _tts(svc: pipeline.Services, text: str, lang: Language) -> dict:
    if not text or not svc.bhashini.configured:
        return {}
    try:
        async with asyncio.timeout(svc.settings.tts_timeout_s):
            audio, mime = await svc.bhashini.tts(text, lang)
        return {"audio_b64": audio, "audio_mime": mime, "audio_text": text}
    except Exception as e:  # noqa: BLE001 - the app falls back to the browser voice
        log.info("tts unavailable: %r", e)
        return {}


@router.post("/ask")
async def ask(
    image: UploadFile = File(...),
    query: str = Form(""),
    lang: Language = Form(Language.en),
    profile: Profile = Form(Profile.visual),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    heading: float | None = Form(None),
    svc: pipeline.Services = Depends(get_services),
):
    img = _as_jpeg(await _read_limited(image, MAX_IMAGE_BYTES, "image"))
    location = (
        Location(lat=lat, lon=lon, heading_deg=heading % 360 if heading is not None else None)
        if lat is not None and lon is not None
        else None
    )
    meta = AnalyzeMetadata(
        session_id="pwa",
        request_id=uuid.uuid4().hex[:16],
        query_text=query.strip()[:500] or None,
        location=location,
        include_audio=False,  # audio is generated below for the exact text the app speaks
    )
    r = await pipeline.run(
        svc, pipeline.PipelineInput(meta=meta, image=img, audio_wav=None, language=lang, profile=profile)
    )
    if r.status == Status.error:
        raise HTTPException(503, r.error or "The assistant could not answer right now.")
    body = to_pwa(r, profile)
    if profile != Profile.hearing:
        # The app speaks `simple` first for older adults, `answer` otherwise.
        first = body["simple"] if profile == Profile.ageing else body["answer"]
        body.update(await _tts(svc, first, r.language))
    return body


@router.post("/tts")
async def tts(
    text: str = Form(...),
    lang: Language = Form(Language.en),
    svc: pipeline.Services = Depends(get_services),
):
    """Bhashini audio for one string. 204 when TTS is unavailable (app uses the browser voice)."""
    out = await _tts(svc, text.strip()[:600], lang)
    if not out:
        return Response(status_code=204)
    return out
