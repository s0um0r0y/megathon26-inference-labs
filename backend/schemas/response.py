"""Response schemas for /api/analyze. /api/ask (the PWA) maps these in api/ask.py:to_pwa."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from schemas.request import Language, Profile


class Intent(StrEnum):
    read_sign = "read_sign"
    bus_route = "bus_route"
    shop_info = "shop_info"
    traffic_signal = "traffic_signal"
    navigation = "navigation"
    emergency = "emergency"
    out_of_scope = "out_of_scope"


class Status(StrEnum):
    ok = "ok"
    # Photo unusable or OCR too uncertain: guide a retake, never guess.
    needs_retake = "needs_retake"
    # Speech recognition uncertain: echo the transcript and ask before acting.
    needs_confirmation = "needs_confirmation"
    cancelled = "cancelled"
    error = "error"


class ConfidenceLevel(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class Stage(StrEnum):
    received = "received"
    listening = "listening"  # ASR
    reading = "reading"  # OCR
    locating = "locating"  # maps
    translating = "translating"
    thinking = "thinking"  # vision LLM
    checking = "checking"  # safety
    speaking = "speaking"  # TTS
    done = "done"


class SessionOut(BaseModel):
    session_id: str
    language: Language
    profile: Profile
    speech_rate: float


class Landmark(BaseModel):
    name: str
    kind: str
    distance_m: int
    # "ahead", "ahead on your right", "behind you"... only when heading is known.
    direction: str | None = None
    bearing_deg: int


class BusRoute(BaseModel):
    ref: str
    name: str | None = None
    to: str | None = None


class ConfidenceReport(BaseModel):
    score: float = Field(ge=0, le=1)
    level: ConfidenceLevel
    sources: dict[str, float] = {}
    reasons: list[str] = []


class Answer(BaseModel):
    """Answer already shaped for the user's profile and translated to their language."""

    short: str  # one sentence that answers the question
    steps: list[str] = []  # one instruction at a time (ageing / navigation)
    details: list[str] = []  # offered on demand ("want the next two buses?")
    simpler: str | None = None  # "Explain simpler" variant
    follow_up: str | None = None  # the "offer more" question
    caution: str | None = None  # safety caution, always present for traffic signals


class HelpOffer(BaseModel):
    message: str
    call_number: str | None = None
    sms_body: str | None = None


class AnalyzeResponse(BaseModel):
    request_id: str
    status: Status
    intent: Intent | None = None
    language: Language
    answer: Answer | None = None
    # Text to speak / caption, in the user's language, in the order it should be delivered.
    spoken_text: str = ""
    audio_b64: str | None = None
    audio_mime: str | None = None
    transcript: str | None = None  # what we heard (user language)
    sign_text: str | None = None  # what we read off the sign (original script)
    retake_hint: str | None = None
    confidence: ConfidenceReport | None = None
    landmarks: list[Landmark] = []
    bus_routes: list[BusRoute] = []
    help: HelpOffer | None = None
    # Plain assistant reply (English), for the raw-vs-accessible comparison view.
    raw_answer: str | None = None
    timings_ms: dict[str, int] = {}
    error: str | None = None


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    request_id: str
    stage: Stage
    message: str


class SpeakResponse(BaseModel):
    audio_b64: str | None
    audio_mime: str | None
    text: str
    language: Language
