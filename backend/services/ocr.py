"""Sign OCR.

Provider order: the IIIT Bhashini sandbox OCR model (if CANVAS_OCR_MODEL is set),
then Google Cloud Vision (if GOOGLE_VISION_API_KEY is set), then a transcription
pass on the vision model. A provider that fails falls through to the next. Either way the result is an
independent reading that evidence_fusion.py cross-checks against the reasoning
model's own `sign_text`.
"""

import base64
import logging
from dataclasses import dataclass

import httpx

from config import Settings
from schemas.request import Language
from services.bhashini import BhashiniError, LanguageClient
from services.vision import VisionClient

log = logging.getLogger(__name__)

GOOGLE_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float  # 0..1
    provider: str


def detect_language(text: str) -> Language | None:
    """Dominant script of a sign reading -> source language for NMT. None if no letters."""
    counts = {Language.te: 0, Language.hi: 0, Language.en: 0}
    for ch in text:
        cp = ord(ch)
        if 0x0C00 <= cp <= 0x0C7F:
            counts[Language.te] += 1
        elif 0x0900 <= cp <= 0x097F:
            counts[Language.hi] += 1
        elif ch.isascii() and ch.isalpha():
            counts[Language.en] += 1
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    return lang if n else None


class OcrClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        vision: VisionClient,
        language: LanguageClient | None = None,
    ):
        self._http = http
        self._s = settings
        self._vision = vision
        self._language = language

    @property
    def provider(self) -> str:
        if self._s.canvas_ocr_model and hasattr(self._language, "ocr"):
            return "bhashini-sandbox"
        if self._s.google_vision_api_key:
            return "google-vision"
        return "vision-llm" if self._vision_fallback else "none"

    @property
    def _vision_fallback(self) -> bool:
        enabled = self._s.ocr_vision_fallback
        if enabled is None:
            enabled = self._s.vision_provider == "anthropic"
        return enabled and self._vision.configured

    async def read(self, image: bytes) -> OcrResult:
        if self.provider == "bhashini-sandbox":
            try:
                text = await self._language.ocr(image)  # type: ignore[union-attr]
                # The sandbox returns no score; an empty read is treated as unreliable.
                return OcrResult(text, 0.7 if text else 0.1, "bhashini-sandbox")
            except (BhashiniError, httpx.HTTPError) as e:
                log.warning("sandbox OCR failed, falling back: %s", e)
        if self._s.google_vision_api_key:
            return await self._google(image)
        if self._vision_fallback:
            text, conf = await self._vision.read_text(image)
            return OcrResult(text, conf, "vision-llm")
        return OcrResult("", 0.0, "none")

    async def _google(self, image: bytes) -> OcrResult:
        resp = await self._http.post(
            GOOGLE_VISION_URL,
            params={"key": self._s.google_vision_api_key},
            json={
                "requests": [
                    {
                        "image": {"content": base64.b64encode(image).decode()},
                        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                        "imageContext": {"languageHints": ["te", "hi", "en"]},
                    }
                ]
            },
        )
        resp.raise_for_status()
        result = resp.json()["responses"][0]
        full = result.get("fullTextAnnotation") or {}
        text = full.get("text", "").strip()
        # Average block confidence across pages; Google reports 0..1 per block.
        confs = [
            block.get("confidence", 0.0)
            for page in full.get("pages", [])
            for block in page.get("blocks", [])
        ]
        conf = sum(confs) / len(confs) if confs else (0.5 if text else 0.0)
        return OcrResult(text, conf, "google-vision")
