"""Applies safety/policies.py to a model answer before it reaches the user.

Runs on the English answer (before NMT) so pattern checks are language-independent.
"""

import re
from dataclasses import dataclass, field, replace

from safety import policies
from safety.confidence import RETAKE_BELOW
from schemas.response import Intent
from services.vision import VisionAnswer


@dataclass
class Validation:
    answer: VisionAnswer
    # Set when the answer must not be delivered as-is.
    force_retake: bool = False
    use_traffic_caution: bool = False
    issues: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?।])\s+", text.strip()) if s]


def _is_unsafe_crossing(text: str) -> bool:
    return any(p.search(text) for p in policies.UNSAFE_CROSSING_PATTERNS)


def _strip_unsafe(text: str) -> str:
    return " ".join(s for s in _sentences(text) if not _is_unsafe_crossing(s))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", policies.MARKDOWN_NOISE.sub("", text)).strip()


def _limit_words(text: str, n: int) -> str:
    sents = _sentences(text)
    if not sents:
        return text
    out = sents[0]
    words = out.split()
    if len(words) > n:
        out = " ".join(words[:n]).rstrip(",;:") + "."
    return out


def unsupported_routes(answer_text: str, evidence: list[str]) -> list[str]:
    """Route tokens named in the answer that appear in none of the evidence texts."""
    haystack = " ".join(evidence).upper()
    tokens = set(policies.ROUTE_TOKEN.findall(answer_text.upper()))
    return sorted(
        t for t in tokens if not re.search(rf"(?<![0-9A-Z]){re.escape(t)}(?![0-9A-Z])", haystack)
    )


def validate(
    answer: VisionAnswer,
    intent: Intent,
    confidence: float,
    evidence_texts: list[str],
) -> Validation:
    a = replace(
        answer,
        short=_clean(answer.short),
        steps=[_clean(s) for s in answer.steps if s.strip()],
        details=[_clean(d) for d in answer.details if d.strip()],
        simpler=_clean(answer.simpler),
        follow_up=_clean(answer.follow_up),
        caution=_clean(answer.caution),
    )
    v = Validation(answer=a)

    # 1. Traffic signals: never declare it safe to cross; always caution.
    if intent == Intent.traffic_signal or a.sign_type == "traffic_signal":
        for name in ("short", "simpler", "follow_up"):
            text = getattr(a, name)
            if _is_unsafe_crossing(text):
                v.issues.append(f"unsafe_crossing_in_{name}")
                setattr(a, name, _strip_unsafe(text))
        unsafe_steps = [s for s in a.steps if _is_unsafe_crossing(s)]
        if unsafe_steps:
            v.issues.append("unsafe_crossing_in_steps")
            a.steps = [s for s in a.steps if not _is_unsafe_crossing(s)]
        a.details = [d for d in a.details if not _is_unsafe_crossing(d)]
        if not a.short:
            # Everything the model said was a crossing instruction; nothing safe to say.
            v.force_retake = True
            v.issues.append("no_safe_signal_description")
        v.use_traffic_caution = True

    # 2. No silent guesses: bus routes must be backed by the sign or map data.
    if intent == Intent.bus_route and a.answerable:
        bad = unsupported_routes(" ".join([a.short, *a.steps]), evidence_texts)
        if bad:
            v.issues.append(f"unverified_routes:{','.join(bad)}")
            a.answerable = False

    # 3. Low confidence or the model itself says it can't answer -> retake.
    if not a.answerable or confidence < RETAKE_BELOW:
        v.force_retake = True
        if confidence < RETAKE_BELOW:
            v.issues.append("low_confidence")

    # 4. Answer-first: the short answer is one sentence.
    if len(a.short.split()) > policies.MAX_SHORT_WORDS or len(_sentences(a.short)) > 1:
        overflow = _sentences(a.short)[1:]
        a.short = _limit_words(a.short, policies.MAX_SHORT_WORDS)
        a.details = overflow + a.details
        v.issues.append("short_trimmed")

    return v
