"""Escalation to a human when the assistant cannot help safely.

Hackathon scope: requests go into an in-memory queue that a volunteer dashboard
(or a team member during the demo) can poll, and the user is always offered the
national emergency number. Swap HelpDesk for a real paging service later.
"""

import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from schemas.request import HelpRequest, Language
from schemas.response import HelpOffer

EMERGENCY_NUMBER = "112"

# Pre-translated so help works even when Bhashini is unreachable.
_MESSAGES = {
    Language.en: {
        "queued": "I have asked a volunteer to help you. If you are in danger, call 112.",
        "emergency": "This sounds urgent. Call 112 now. I can share your location by SMS.",
        "low_confidence": "I could not read this sign reliably. Would you like a volunteer to help?",
        "sms": "I need help. My location: {link}",
    },
    Language.hi: {
        "queued": "मैंने एक स्वयंसेवक से आपकी मदद करने को कहा है। खतरे में हों तो 112 पर कॉल करें।",
        "emergency": "यह ज़रूरी लगता है। अभी 112 पर कॉल करें। मैं SMS से आपकी लोकेशन भेज सकता हूँ।",
        "low_confidence": "मैं यह बोर्ड ठीक से नहीं पढ़ पाया। क्या आप किसी स्वयंसेवक से मदद चाहेंगे?",
        "sms": "मुझे मदद चाहिए। मेरी लोकेशन: {link}",
    },
    Language.te: {
        "queued": "మీకు సహాయం చేయమని ఒక వాలంటీర్‌ను అడిగాను. ప్రమాదంలో ఉంటే 112కు కాల్ చేయండి.",
        "emergency": "ఇది అత్యవసరంగా ఉంది. వెంటనే 112కు కాల్ చేయండి. మీ లొకేషన్‌ను SMS ద్వారా పంపగలను.",
        "low_confidence": "ఈ బోర్డును సరిగ్గా చదవలేకపోయాను. వాలంటీర్ సహాయం కావాలా?",
        "sms": "నాకు సహాయం కావాలి. నా లొకేషన్: {link}",
    },
}


@dataclass
class HelpTicket:
    id: str
    session_id: str
    reason: str
    created: float
    lat: float | None = None
    lon: float | None = None
    note: str | None = None
    status: str = "open"


@dataclass
class HelpDesk:
    tickets: deque[HelpTicket] = field(default_factory=lambda: deque(maxlen=200))

    def offer(self, reason: str, lang: Language, lat: float | None = None, lon: float | None = None) -> HelpOffer:
        msgs = _MESSAGES[lang]
        link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}" if lat is not None else ""
        return HelpOffer(
            message=msgs.get(reason, msgs["queued"]),
            call_number=EMERGENCY_NUMBER,
            sms_body=msgs["sms"].format(link=link) if link else None,
        )

    def submit(self, req: HelpRequest, lang: Language) -> tuple[HelpTicket, HelpOffer]:
        ticket = HelpTicket(
            id=uuid.uuid4().hex[:12],
            session_id=req.session_id,
            reason=req.reason,
            created=time.time(),
            lat=req.location.lat if req.location else None,
            lon=req.location.lon if req.location else None,
            note=req.note,
        )
        self.tickets.append(ticket)
        offer_reason = "emergency" if req.reason == "emergency" else "queued"
        return ticket, self.offer(offer_reason, lang, ticket.lat, ticket.lon)

    def open_tickets(self) -> list[HelpTicket]:
        return [t for t in self.tickets if t.status == "open"]
