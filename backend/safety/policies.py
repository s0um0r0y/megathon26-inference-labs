"""Declarative safety policies. validator.py enforces them; tests/test_safety.py pins them.

Policy texts are pre-translated so safety messaging never depends on NMT succeeding.
"""

import re

from schemas.request import Language

# Anything that tells or implies the user may cross. Signal readings are
# informational only: the system must never declare it safe to cross.
UNSAFE_CROSSING_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bsafe to (cross|walk|go)\b",
        r"\b(it is|it's|you are|you're) (safe|clear|okay|ok|fine)\b",
        r"\byou (can|may|should|could) (now )?(cross|walk|go|proceed)\b",
        r"\b(go ahead|proceed|start walking|walk now|cross now)\b",
        r"\b(cross|walk) (the road|the street)? ?(now|safely)\b",
        r"\bno (cars|traffic|vehicles) (are )?coming\b",
        r"\broad is clear\b",
    ]
]

TRAFFIC_CAUTION = {
    Language.en: "This is only what the signal shows. Listen for traffic and check with people nearby before you cross.",
    Language.hi: "यह सिर्फ़ सिग्नल की जानकारी है। सड़क पार करने से पहले ट्रैफ़िक की आवाज़ सुनें और आसपास के लोगों से पूछें।",
    Language.te: "ఇది సిగ్నల్‌లో కనిపించేది మాత్రమే. రోడ్డు దాటే ముందు ట్రాఫిక్ శబ్దం వినండి, దగ్గర ఉన్నవారిని అడగండి.",
}

OUT_OF_SCOPE_REPLY = {
    Language.en: "I can only help with signs, buses and directions. For this, please ask a doctor, lawyer or bank you trust.",
    Language.hi: "मैं सिर्फ़ बोर्ड, बस और रास्ते में मदद कर सकता हूँ। इसके लिए किसी भरोसेमंद डॉक्टर, वकील या बैंक से पूछें।",
    Language.te: "నేను బోర్డులు, బస్సులు, దారి విషయంలో మాత్రమే సహాయం చేయగలను. దీని కోసం నమ్మకమైన డాక్టర్, లాయర్ లేదా బ్యాంకును అడగండి.",
}

UNVERIFIED_ROUTE_REPLY = {
    Language.en: "I can't confirm that bus number from this photo, so I won't guess.",
    Language.hi: "इस फ़ोटो से मैं बस नंबर पक्का नहीं कर पा रहा, इसलिए अंदाज़ा नहीं लगाऊँगा।",
    Language.te: "ఈ ఫోటో నుండి బస్ నంబర్‌ను నిర్ధారించలేకపోతున్నాను, కాబట్టి ఊహించను.",
}

GENERIC_RETAKE_HINT = {
    Language.en: "Hold the phone steady, point it at the board, and try again.",
    Language.hi: "फ़ोन को स्थिर रखें, बोर्ड की तरफ़ करें और फिर से कोशिश करें।",
    Language.te: "ఫోన్‌ను కదలకుండా బోర్డు వైపు పెట్టి మళ్లీ ప్రయత్నించండి.",
}

CONFIRM_TRANSCRIPT = {
    Language.en: "Did you ask: {q}? Say yes or tap confirm.",
    Language.hi: "क्या आपने पूछा: {q}? हाँ कहें या पुष्टि दबाएँ।",
    Language.te: "మీరు అడిగింది ఇదేనా: {q}? అవును అనండి లేదా నిర్ధారించు నొక్కండి.",
}

DID_NOT_HEAR = {
    Language.en: "I didn't catch that. Please say your question again, or choose one from the list.",
    Language.hi: "मैं सुन नहीं पाया। कृपया फिर से पूछें, या सूची से कोई सवाल चुनें।",
    Language.te: "నాకు వినిపించలేదు. దయచేసి మళ్లీ అడగండి, లేదా జాబితా నుండి ఒక ప్రశ్న ఎంచుకోండి.",
}

# Matched against the English query (after NMT). "pharmacy" alone is a shop
# question, not medical advice, so only advice-seeking phrasing is listed.
OUT_OF_SCOPE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(which|what) (medicine|tablet|drug)s?\b",
        r"\b(dose|dosage)\b",
        r"\bshould i take\b",
        r"\b(diagnos\w*|symptom\w*)\b",
        r"\b(lawyer|legal advice|sue|lawsuit|court case)\b",
        r"\b(invest\w*|stock market|shares|loan|interest rate|insurance claim)\b",
    ]
]

EMERGENCY_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(emergency|accident|fire|hurt|injured|bleeding|attack\w*|danger|unsafe)\b",
        r"\b(ambulance|police|help me)\b",
        r"\b(exit|way out|evacuat\w*)\b",
    ]
]

# Bus route numbers such as "219", "10H", "5K/M", only where the answer names them
# as a bus/route (so distances and timings are not mistaken for routes). Used to
# check that any route named in an answer appears in the evidence.
ROUTE_TOKEN = re.compile(
    r"\b(?:bus(?:es)?|route|no\.?)\s*(?:number\s*)?(\d{1,4}[A-Z]{0,2}(?:/[A-Z0-9]{1,3})?)\b",
    re.IGNORECASE,
)

MAX_SHORT_WORDS = 30
MARKDOWN_NOISE = re.compile(r"[*_#`|>\[\]]+")
