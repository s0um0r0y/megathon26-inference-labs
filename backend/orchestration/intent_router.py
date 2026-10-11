"""Keyword intent routing on the English (post-NMT) question.

Deterministic on purpose: the intent decides which safety rules apply, so it
must not depend on a model call that can fail or drift. The vision model also
gets the intent as a hint and reports its own `sign_type`, which the validator
checks too (a photo of a signal triggers signal rules whatever the question).
"""

import re

from safety import policies
from schemas.response import Intent

_RULES: list[tuple[Intent, re.Pattern]] = [
    (
        Intent.traffic_signal,
        re.compile(
            r"\b(signal|traffic light|light (is|showing)|cross(ing)?|zebra|walk(ing)? sign|"
            r"green man|red man|pedestrian)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.bus_route,
        re.compile(r"\b(bus(es)?|route|which (number|no)|depot|stop for|go(es)? to)\b", re.IGNORECASE),
    ),
    (
        Intent.shop_info,
        re.compile(
            r"\b(shop|store|open|closed?|timings?|hours|what (is|kind of) (this|that) (place|shop)|"
            r"pharmacy|hotel|restaurant|bank|atm|sell)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.navigation,
        re.compile(
            r"\b(where( is|'s)?|nearest|how (do|can) i (get|go|reach)|way to|direction|near(by)?|"
            r"left or right|which side|platform)\b",
            re.IGNORECASE,
        ),
    ),
]


def route(question_en: str, sign_text_en: str = "") -> Intent:
    q = question_en.strip()
    if any(p.search(q) for p in policies.EMERGENCY_PATTERNS):
        return Intent.emergency
    if any(p.search(q) for p in policies.OUT_OF_SCOPE_PATTERNS):
        return Intent.out_of_scope
    for intent, pattern in _RULES:
        if pattern.search(q):
            return intent
    # No usable question (e.g. "what is this?"): let the sign decide.
    if sign_text_en and _RULES[0][1].search(sign_text_en):
        return Intent.traffic_signal
    return Intent.read_sign
