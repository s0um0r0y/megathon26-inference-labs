"""Request schemas. These mirror frontend/src/services/api.ts - keep them in sync."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Language(StrEnum):
    en = "en"
    hi = "hi"
    te = "te"


class Profile(StrEnum):
    """Condition profile driving how answers are shaped (see accessibility adapter)."""

    default = "default"
    visual = "visual"
    hearing = "hearing"
    ageing = "ageing"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    # Compass heading of the phone's back camera, degrees clockwise from north.
    heading_deg: float | None = Field(default=None, ge=0, lt=360)


class FrameQuality(BaseModel):
    """Stats from frontend/src/workers/frameQuality.worker.ts for the uploaded frame."""

    brightness: float = Field(ge=0, le=255)
    blur_score: float = Field(ge=0)
    motion: float = Field(ge=0)
    stable_frames: int = Field(ge=0)


class SessionCreate(BaseModel):
    language: Language = Language.en
    profile: Profile = Profile.default
    speech_rate: float = Field(default=1.0, ge=0.5, le=2.0)


class SessionUpdate(BaseModel):
    language: Language | None = None
    profile: Profile | None = None
    speech_rate: float | None = Field(default=None, ge=0.5, le=2.0)


class AnalyzeMetadata(BaseModel):
    """JSON part of the multipart /api/analyze request (image and audio are file parts)."""

    session_id: str
    request_id: str = Field(min_length=4, max_length=64)
    query_text: str | None = Field(default=None, max_length=500)
    # The user confirmed a previously echoed transcript; skip the ASR confirmation gate.
    confirmed: bool = False
    # Answer in a language other than the one spoken (doc section 4: "User controls").
    answer_language: Language | None = None
    location: Location | None = None
    frame_quality: FrameQuality | None = None
    include_audio: bool = True


class HelpRequest(BaseModel):
    session_id: str
    reason: Literal["user_requested", "low_confidence", "emergency"] = "user_requested"
    location: Location | None = None
    note: str | None = Field(default=None, max_length=300)


class SpeakRequest(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=600)
    language: Language | None = None


class ClientWsMessage(BaseModel):
    type: Literal["cancel", "ping"]
    request_id: str | None = None
