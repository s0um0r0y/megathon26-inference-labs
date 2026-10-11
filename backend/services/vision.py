"""Vision reasoning over raw HTTP (httpx) with structured JSON output: Claude, or an
open model (Llama, Qwen, Gemma) behind any OpenAI-compatible server.

The model sees the sign photo, the independent OCR reading, the user's question
(in English), the routed intent, the condition profile and nearby map context,
and returns a structured answer. The model writes in English; translation to the
user's language happens afterwards via Bhashini NMT.
"""

import base64
import json
import logging
from dataclasses import dataclass, field

import httpx

from config import Settings
from schemas.request import Profile
from schemas.response import Intent

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"


class VisionError(RuntimeError):
    pass


class VisionRefusal(VisionError):
    pass


# Accessibility rubric. Profile-specific rules are appended per request.
SYSTEM_PROMPT = """\
You are the reasoning engine inside SignSaathi, an assistant that helps blind, \
deaf and older pedestrians in Indian cities understand street signs, bus boards, \
shop boards and pedestrian signals from a single phone photo.

How to answer:
- Answer exactly the question asked, in one short sentence first. Do not read out \
the whole board. Example: "Bus 219 goes to Secunderabad station; it is the third \
route listed."
- Put anything extra in `details`, and offer it with a short `follow_up` question \
instead of listing it.
- Convert tables, timetables and route maps into a spoken summary. Never use \
markdown, symbols, tables or emoji: every string will be read aloud by text-to-speech.
- Use plain everyday words. Say directions relative to the user ("on your right", \
"30 metres ahead") when the context gives them.
- `simpler` restates `short` for someone confused: very short sentences, no numbers \
beyond what is essential.

Honesty rules (these matter more than being helpful):
- Only state what is visible in the photo or given in the context. If the text \
needed to answer is cut off, blurred or too small to read, set `answerable` to \
false, explain what you can and cannot read in `short`, and give a `retake_hint` \
naming the actual problem you see (which edge is cut off, too dark, too far away).
- If the sign is readable but simply does not contain what was asked (for example \
no listed bus goes to that place), that is a real answer: set `answerable` to true \
and say so plainly, mentioning what the sign does list. Leave `retake_hint` empty.
- Leave `retake_hint` empty whenever the photo is fine.
- Never guess a bus route, number, timing or direction.
- `sign_text` is your own transcription of all legible text on the sign, \
line by line, in the original script.

Safety rules:
- For traffic lights and pedestrian signals, describe only what the signal shows. \
Never say or imply that it is safe to cross, and never tell the user to cross or \
walk. Always set `caution`, telling them to listen for traffic and check with \
people nearby before crossing.
- Do not give medical, legal or financial advice. If asked, say you can only help \
with signs and directions.
- For emergency, exit or platform signs, state where the sign points first.
"""

PROFILE_RULES = {
    Profile.visual: (
        "The user is blind or has low vision and will only hear the answer. "
        "Mention distances and directions. If the photo is badly framed, the "
        "retake_hint must say how to move the phone (left, right, up, down, closer)."
    ),
    Profile.hearing: (
        "The user is deaf or hard of hearing and will read the answer as captions. "
        "Keep `short` under 15 words. Mention anything that is usually announced "
        "by sound (bus arrivals, signal beeps)."
    ),
    Profile.ageing: (
        "The user is an older adult who may be unfamiliar with smartphones. Use "
        "short, slow, friendly sentences. Put multi-step guidance in `steps`, one "
        "action per step, at most four steps."
    ),
    Profile.default: "Keep answers short and practical.",
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "short": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "array", "items": {"type": "string"}},
        "simpler": {"type": "string"},
        "follow_up": {"type": "string"},
        "caution": {"type": "string"},
        "retake_hint": {"type": "string"},
        "sign_text": {"type": "string"},
        "sign_type": {
            "type": "string",
            "enum": [
                "bus_board",
                "shop_board",
                "traffic_signal",
                "street_sign",
                "emergency_or_exit",
                "other",
                "none",
            ],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "plain_reply": {"type": "string"},
    },
    "required": [
        "answerable",
        "short",
        "steps",
        "details",
        "simpler",
        "follow_up",
        "caution",
        "retake_hint",
        "sign_text",
        "sign_type",
        "confidence",
        "plain_reply",
    ],
    "additionalProperties": False,
}

OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {"type": "array", "items": {"type": "string"}},
        "legibility": {"type": "string", "enum": ["clear", "partial", "illegible"]},
    },
    "required": ["lines", "legibility"],
    "additionalProperties": False,
}

_CONFIDENCE_SCORE = {"high": 0.9, "medium": 0.65, "low": 0.3}


@dataclass
class VisionAnswer:
    answerable: bool
    short: str
    steps: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    simpler: str = ""
    follow_up: str = ""
    caution: str = ""
    retake_hint: str = ""
    sign_text: str = ""
    sign_type: str = "other"
    confidence: float = 0.5
    plain_reply: str = ""


def _coerce_answer(data: dict) -> VisionAnswer:
    """Normalise model JSON into a VisionAnswer.

    Claude's structured output always matches ANSWER_SCHEMA; open models served
    through OpenAI-compatible endpoints may drop fields or use the wrong types,
    so every field gets a safe default. A missing `answerable` counts as False:
    an unsure parse must lead to a retake, never to a confident answer.
    """

    def text(key: str) -> str:
        v = data.get(key)
        return v.strip() if isinstance(v, str) else ""

    def items(key: str) -> list[str]:
        v = data.get(key)
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v or [] if str(x).strip()] if isinstance(v, list) else []

    sign_type = text("sign_type")
    allowed = ANSWER_SCHEMA["properties"]["sign_type"]["enum"]
    return VisionAnswer(
        answerable=data.get("answerable") is True,
        short=text("short"),
        steps=items("steps"),
        details=items("details"),
        simpler=text("simpler"),
        follow_up=text("follow_up"),
        caution=text("caution"),
        retake_hint=text("retake_hint"),
        sign_text=text("sign_text"),
        sign_type=sign_type if sign_type in allowed else "other",
        confidence=_CONFIDENCE_SCORE.get(text("confidence").lower(), 0.3),
        plain_reply=text("plain_reply"),
    )


def _parse_json(text: str) -> dict:
    """Parse model JSON, tolerating markdown fences some open models add."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < start:
        raise VisionError("model returned no JSON object")
    try:
        data = json.loads(t[start : end + 1])
    except json.JSONDecodeError as e:
        raise VisionError(f"model returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise VisionError("model JSON is not an object")
    return data


def _downscale(image: bytes, max_side: int) -> bytes:
    """Shrink a JPEG so its longer side is at most max_side. Returns the input on any problem."""
    if max_side <= 0:
        return image
    try:
        import io

        from PIL import Image

        im = Image.open(io.BytesIO(image))
        if max(im.size) <= max_side:
            return image
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=85)
        return out.getvalue()
    except Exception:  # noqa: BLE001 - never fail a request over resizing
        return image


class VisionClient:
    """Vision reasoning over one of two backends, chosen by VISION_PROVIDER:

    - "anthropic": Claude Messages API with schema-constrained output.
    - "openai_compat": any OpenAI-compatible /chat/completions server with image
      input - Ollama or vLLM running Llama/Qwen/Gemma locally, or hosted Llama on
      Groq/Together/OpenRouter.

    The safety validator runs on the output either way; it does not trust the model.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._s = settings
        # Some OpenAI-compatible servers reject or loop on json_schema; remember and downgrade.
        self._schema_supported = settings.openai_json_mode == "json_schema"

    @property
    def configured(self) -> bool:
        if self._s.vision_provider == "openai_compat":
            return bool(self._s.openai_base_url and self._s.openai_model)
        return bool(self._s.anthropic_api_key)

    @property
    def label(self) -> str:
        if self._s.vision_provider == "openai_compat":
            return f"openai_compat:{self._s.openai_model}"
        return f"anthropic:{self._s.anthropic_model}"

    async def _call(self, system: str, image: bytes, text: str, schema: dict, max_tokens: int) -> dict:
        if self._s.vision_provider == "openai_compat":
            return await self._call_openai_compat(system, image, text, schema, max_tokens)
        return await self._call_anthropic(system, image, text, schema, max_tokens)

    async def _call_anthropic(
        self, system: str, image: bytes, text: str, schema: dict, max_tokens: int
    ) -> dict:
        resp = await self._http.post(
            API_URL,
            timeout=self._s.vision_timeout_s,
            headers={
                "x-api-key": self._s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                # Server-side fallback: if a safety classifier declines (rare for
                # street signs), the API retries on Anthropic's recommended model.
                "anthropic-beta": "server-side-fallback-2026-07-01",
                "content-type": "application/json",
            },
            json={
                "model": self._s.anthropic_model,
                "max_tokens": max_tokens,
                "fallbacks": "default",
                "system": system,
                "output_config": {
                    "effort": self._s.anthropic_effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64.b64encode(image).decode(),
                                },
                            },
                            {"type": "text", "text": text},
                        ],
                    }
                ],
            },
        )
        if resp.status_code >= 400:
            raise VisionError(f"Claude API {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        stop = body.get("stop_reason")
        if stop == "refusal":
            raise VisionRefusal("model declined the request")
        if stop == "max_tokens":
            raise VisionError("model output truncated")
        out = next((b["text"] for b in body.get("content", []) if b.get("type") == "text"), None)
        if out is None:
            raise VisionError("no text block in response")
        return json.loads(out)

    async def _call_openai_compat(
        self, system: str, image: bytes, text: str, schema: dict, max_tokens: int
    ) -> dict:
        url = self._s.openai_base_url.rstrip("/") + "/chat/completions"
        headers = {"content-type": "application/json"}
        if self._s.openai_api_key:
            headers["authorization"] = f"Bearer {self._s.openai_api_key}"
        data_uri = "data:image/jpeg;base64," + base64.b64encode(
            _downscale(image, self._s.vision_max_side)
        ).decode()
        body = {
            "model": self._s.openai_model,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": text},
                    ],
                },
            ],
        }

        def with_format(schema_mode: bool) -> dict:
            if schema_mode:
                fmt = {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema, "strict": True}}
                return {**body, "response_format": fmt}
            # json_object mode: the schema goes in the prompt instead.
            msgs = list(body["messages"])
            msgs[0] = {
                "role": "system",
                "content": f"{system}\n\nReply with only a JSON object matching this schema:\n{json.dumps(schema)}",
            }
            return {**body, "messages": msgs, "response_format": {"type": "json_object"}}

        # Per-request timeout: the shared client's default is shorter than a local model needs.
        timeout = self._s.vision_timeout_s
        resp = await self._http.post(url, headers=headers, json=with_format(self._schema_supported), timeout=timeout)
        rejected = resp.status_code == 400 and "response_format" in resp.text
        looped = resp.status_code >= 500 and "repeat" in resp.text  # Ollama grammar loop
        if self._schema_supported and (rejected or looped):
            log.info("%s failed with json_schema; falling back to json_object", self.label)
            self._schema_supported = False
            resp = await self._http.post(url, headers=headers, json=with_format(False), timeout=timeout)
        if resp.status_code >= 400:
            raise VisionError(f"{self.label} {resp.status_code}: {resp.text[:300]}")
        try:
            choice = resp.json()["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise VisionError("malformed chat completion") from e
        if choice.get("finish_reason") == "length":
            raise VisionError("model output truncated")
        return _parse_json(content or "")

    async def answer(
        self,
        image: bytes,
        question_en: str,
        intent: Intent,
        profile: Profile,
        ocr_text: str,
        map_context: str,
    ) -> VisionAnswer:
        system = f"{SYSTEM_PROMPT}\nAbout this user: {PROFILE_RULES[profile]}"
        context = [
            f"User question (translated to English): {question_en or 'What does this sign say?'}",
            f"Likely intent: {intent.value}",
            f"Independent OCR reading of the photo (may contain errors): {ocr_text or '(none)'}",
        ]
        if map_context:
            context.append(f"Nearby places from OpenStreetMap:\n{map_context}")
        context.append(
            "`plain_reply` is how a generic assistant would answer with no accessibility "
            "adaptation (used only for comparison testing)."
        )
        data = await self._call(system, image, "\n\n".join(context), ANSWER_SCHEMA, max_tokens=4000)
        return _coerce_answer(data)

    async def read_text(self, image: bytes) -> tuple[str, float]:
        """OCR fallback when no dedicated OCR provider is configured."""
        data = await self._call(
            "Transcribe all legible text in the photo, line by line, in the original "
            "script (Telugu, Hindi/Devanagari, English or other). Do not translate, "
            "do not guess illegible text.",
            image,
            "Transcribe the sign.",
            OCR_SCHEMA,
            max_tokens=1500,
        )
        lines = data.get("lines") if isinstance(data.get("lines"), list) else []
        score = {"clear": 0.85, "partial": 0.5, "illegible": 0.1}.get(str(data.get("legibility")), 0.3)
        return "\n".join(str(x) for x in lines), score
