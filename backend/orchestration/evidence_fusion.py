"""Fuses the independent evidence sources into one sign reading and confidence.

Sources: dedicated OCR, the vision model's own transcription and self-rated
confidence, on-device frame quality, and map data. Two independent readings
that agree are strong evidence; disagreement lowers confidence and is reported.
"""

from dataclasses import dataclass

from safety import confidence as conf
from schemas.request import FrameQuality
from schemas.response import ConfidenceReport
from services.maps import MapContext
from services.ocr import OcrResult
from services.vision import VisionAnswer


@dataclass
class FusedEvidence:
    sign_text: str
    confidence: ConfidenceReport
    # Texts a factual claim may be grounded in (validator checks bus routes against these).
    grounding: list[str]


def fuse(
    vision: VisionAnswer,
    ocr: OcrResult | None,
    frame: FrameQuality | None,
    maps: MapContext | None,
) -> FusedEvidence:
    reasons: list[str] = []
    if ocr is not None and ocr.provider == "none":
        ocr = None  # no OCR service configured: absence of a reading is not evidence
    ocr_text = ocr.text if ocr else ""
    agreement = conf.text_agreement(ocr_text, vision.sign_text)

    if agreement is not None and agreement < 0.4:
        reasons.append("ocr_and_vision_disagree")
    if ocr and ocr.confidence < 0.4:
        reasons.append("ocr_low_confidence")
    frame_score = conf.frame_confidence(frame)
    if frame_score < 0.6:
        reasons.append("poor_frame_quality")
    if not vision.answerable:
        reasons.append("model_cannot_answer")

    vision_score = vision.confidence if vision.answerable else min(vision.confidence, 0.25)
    report = conf.combine(
        {
            "vision": vision_score,
            "ocr": ocr.confidence if ocr else None,
            "agreement": agreement,
            "frame": frame_score if frame else None,
        },
        reasons,
    )

    # Prefer the dedicated OCR transcript when it is confident; the model's
    # transcription is the fallback (it reads stylised boards better).
    if ocr and ocr_text and ocr.confidence >= 0.6:
        sign_text = ocr_text
    else:
        sign_text = vision.sign_text or ocr_text

    grounding = [t for t in (ocr_text, vision.sign_text) if t]
    if maps:
        grounding.append(" ".join(f"{r.ref} {r.to or ''}" for r in maps.bus_routes))
    return FusedEvidence(sign_text=sign_text, confidence=report, grounding=grounding)
