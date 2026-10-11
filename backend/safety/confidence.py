"""Confidence scoring for each evidence source and their combination.

Scores are 0..1. Thresholds here decide when the pipeline asks the user to
confirm a transcript or retake a photo instead of answering.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from schemas.request import FrameQuality
from schemas.response import ConfidenceLevel, ConfidenceReport

ASR_CONFIRM_BELOW = 0.6
RETAKE_BELOW = 0.35
HIGH_AT = 0.75

# Matches the frontend worker's thresholds (frameQuality.worker.ts).
MIN_BRIGHTNESS, MAX_BRIGHTNESS = 45, 225
MIN_BLUR_SCORE = 60.0


def asr_confidence(text: str) -> float:
    """Bhashini ASR returns no score, so estimate one from the transcript shape.

    Empty or one-word transcripts and heavy token repetition (a common
    hallucination on noisy audio) are treated as unreliable.
    """
    words = text.split()
    if not words:
        return 0.0
    if len(words) == 1:
        return 0.45
    unique_ratio = len(set(w.lower() for w in words)) / len(words)
    score = 0.85
    if unique_ratio < 0.5:
        score -= 0.4
    if len(words) > 40:
        score -= 0.2
    return max(0.0, min(1.0, score))


def frame_confidence(fq: FrameQuality | None) -> float:
    if fq is None:
        return 0.7  # unknown, don't punish
    score = 1.0
    if fq.brightness < MIN_BRIGHTNESS or fq.brightness > MAX_BRIGHTNESS:
        score -= 0.35
    if fq.blur_score < MIN_BLUR_SCORE:
        score -= 0.4 * (1 - fq.blur_score / MIN_BLUR_SCORE)
    if fq.motion > 12:
        score -= 0.2
    return max(0.0, score)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text)).strip()


def text_agreement(a: str, b: str) -> float | None:
    """Similarity of two independent readings of the sign. None if either is empty."""
    a, b = _normalize(a), _normalize(b)
    if not a or not b:
        return None
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def level_for(score: float) -> ConfidenceLevel:
    if score >= HIGH_AT:
        return ConfidenceLevel.high
    if score >= RETAKE_BELOW:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low


def combine(sources: dict[str, float | None], reasons: list[str]) -> ConfidenceReport:
    """Weighted mean over available sources, then capped by the weakest critical one.

    The cap means a sharp model answer can't hide a photo that is too dark to read.
    """
    weights = {"vision": 0.45, "ocr": 0.2, "agreement": 0.2, "frame": 0.15}
    present = {k: v for k, v in sources.items() if v is not None and k in weights}
    if not present:
        return ConfidenceReport(score=0.0, level=ConfidenceLevel.low, sources={}, reasons=reasons)
    total_w = sum(weights[k] for k in present)
    score = sum(weights[k] * v for k, v in present.items()) / total_w
    critical = [present[k] for k in ("vision", "frame") if k in present]
    if critical:
        score = min(score, min(critical) + 0.15)
    score = round(max(0.0, min(1.0, score)), 3)
    return ConfidenceReport(
        score=score,
        level=level_for(score),
        sources={k: round(v, 3) for k, v in present.items()},
        reasons=reasons,
    )
