"""The SignSaathi pipeline:

    ASR + OCR + maps (parallel)
      -> [confirm transcript if unsure]
      -> NMT to English (parallel)
      -> intent routing
      -> vision reasoning
      -> evidence fusion -> safety validation -> accessibility shaping
      -> NMT to the user's language -> TTS

Every external call is wrapped in its own deadline and degrades softly (a failed
map lookup must not cost the user their answer), all inside one overall request
deadline. Cancellation (from the WebSocket) propagates through the TaskGroups.
"""

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx

from config import Settings
from orchestration import evidence_fusion, intent_router
from safety import policies, validator
from safety.confidence import ASR_CONFIRM_BELOW
from schemas.request import AnalyzeMetadata, Language, Profile
from schemas.response import (
    AnalyzeResponse,
    Answer,
    ConfidenceLevel,
    ConfidenceReport,
    Intent,
    Stage,
    Status,
)
from services.bhashini import AsrResult, LanguageClient, make_language_client
from services.human_help import HelpDesk
from services.maps import MapContext, MapsClient
from services.ocr import OcrClient, OcrResult, detect_language
from services.vision import VisionAnswer, VisionClient, VisionError, VisionRefusal

log = logging.getLogger(__name__)

T = TypeVar("T")
Emit = Callable[[Stage, str], Awaitable[None]]


@dataclass
class Services:
    settings: Settings
    http: httpx.AsyncClient
    bhashini: LanguageClient
    vision: VisionClient
    ocr: OcrClient
    maps: MapsClient
    helpdesk: HelpDesk

    @classmethod
    def create(cls, settings: Settings, http: httpx.AsyncClient) -> "Services":
        vision = VisionClient(http, settings)
        language = make_language_client(http, settings)
        return cls(
            settings=settings,
            http=http,
            bhashini=language,
            vision=vision,
            ocr=OcrClient(http, settings, vision, language),
            maps=MapsClient(http, settings),
            helpdesk=HelpDesk(),
        )


@dataclass
class PipelineInput:
    meta: AnalyzeMetadata
    image: bytes
    audio_wav: bytes | None
    language: Language  # spoken / input language
    profile: Profile


@dataclass
class _Run:
    """Per-request bookkeeping."""

    errors: dict[str, str] = field(default_factory=dict)
    timings: dict[str, int] = field(default_factory=dict)

    async def soft(self, name: str, coro: Awaitable[T], timeout_s: float) -> T | None:
        """Run one external step with its own deadline; failure -> None, recorded.

        CancelledError is deliberately not caught: user cancellation and the
        overall request deadline must still tear everything down.
        """
        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                return await coro
        except TimeoutError:
            self.errors[name] = "timeout"
        except Exception as e:  # noqa: BLE001 - any provider failure degrades softly
            log.warning("%s failed: %r", name, e)
            self.errors[name] = type(e).__name__
        finally:
            self.timings[name] = round((time.perf_counter() - t0) * 1000)
        return None


async def _noop(*_args) -> None:
    return None


async def run(svc: Services, inp: PipelineInput, emit: Emit = _noop) -> AnalyzeResponse:
    s = svc.settings
    meta = inp.meta
    out_lang = meta.answer_language or inp.language
    r = _Run()
    t_start = time.perf_counter()

    def response(status: Status, **kw) -> AnalyzeResponse:
        r.timings["total"] = round((time.perf_counter() - t_start) * 1000)
        return AnalyzeResponse(
            request_id=meta.request_id, status=status, language=kw.pop("language", out_lang),
            timings_ms=r.timings, **kw,
        )

    try:
        async with asyncio.timeout(s.request_deadline_s):
            # ---- 1. Understand: ASR, OCR and maps in parallel --------------------
            await emit(Stage.reading, "Reading the sign")
            asr_task = ocr_task = maps_task = None
            async with asyncio.TaskGroup() as tg:
                if inp.audio_wav and not meta.confirmed and svc.bhashini.configured:
                    await emit(Stage.listening, "Understanding your question")
                    asr_task = tg.create_task(r.soft(
                        "asr",
                        svc.bhashini.asr(base64.b64encode(inp.audio_wav).decode(), inp.language),
                        s.asr_timeout_s,
                    ))
                ocr_task = tg.create_task(r.soft("ocr", svc.ocr.read(inp.image), s.ocr_timeout_s))
                if meta.location:
                    await emit(Stage.locating, "Checking what is nearby")
                    maps_task = tg.create_task(
                        r.soft("maps", svc.maps.context(meta.location), s.maps_timeout_s)
                    )
            asr: AsrResult | None = asr_task.result() if asr_task else None
            ocr: OcrResult | None = ocr_task.result()
            maps: MapContext | None = maps_task.result() if maps_task else None

            # ---- 2. Confirmation gate for uncertain speech ------------------------
            question = (meta.query_text or "").strip()
            transcript = None
            if asr is not None:
                transcript = asr.text
                if not question:
                    question = asr.text
                if asr.confidence < ASR_CONFIRM_BELOW and not meta.query_text:
                    msg = (
                        policies.CONFIRM_TRANSCRIPT[inp.language].format(q=asr.text)
                        if asr.text
                        else policies.DID_NOT_HEAR[inp.language]
                    )
                    audio = await _speak(svc, r, msg, inp.language, inp.profile, meta.include_audio)
                    return response(
                        Status.needs_confirmation, language=inp.language, transcript=asr.text,
                        spoken_text=msg, **audio,
                    )
            elif inp.audio_wav and not question and not meta.confirmed:
                # Audio was sent but ASR is unavailable/failed and there's no text.
                msg = policies.DID_NOT_HEAR[inp.language]
                return response(Status.needs_confirmation, language=inp.language, spoken_text=msg)

            # ---- 3. Translate question and sign text to English -------------------
            await emit(Stage.translating, "Translating")
            sign_lang = detect_language(ocr.text) if ocr and ocr.text else None
            q_en, sign_en = question, ""
            if svc.bhashini.configured:
                async with asyncio.TaskGroup() as tg:
                    q_task = tg.create_task(r.soft(
                        "nmt_in", svc.bhashini.translate(question, inp.language, Language.en),
                        s.nmt_timeout_s,
                    )) if question and inp.language != Language.en else None
                    sign_task = tg.create_task(r.soft(
                        "nmt_sign", svc.bhashini.translate(ocr.text, sign_lang, Language.en),
                        s.nmt_timeout_s,
                    )) if sign_lang and sign_lang != Language.en else None
                if q_task:
                    q_en = q_task.result() or question
                if sign_task:
                    sign_en = sign_task.result() or ""

            # ---- 4. Route intent; out-of-scope never reaches the model ------------
            intent = intent_router.route(q_en, sign_en or (ocr.text if ocr else ""))
            help_offer = None
            if intent == Intent.out_of_scope:
                msg = policies.OUT_OF_SCOPE_REPLY[out_lang]
                audio = await _speak(svc, r, msg, out_lang, inp.profile, meta.include_audio)
                return response(
                    Status.ok, intent=intent, answer=Answer(short=msg), spoken_text=msg,
                    transcript=transcript, **audio,
                )
            if intent == Intent.emergency:
                loc = meta.location
                help_offer = svc.helpdesk.offer(
                    "emergency", out_lang, loc.lat if loc else None, loc.lon if loc else None
                )

            # ---- 5. Reason over the photo -----------------------------------------
            if not svc.vision.configured:
                return response(
                    Status.error, intent=intent, transcript=transcript, help=help_offer,
                    error="Vision model not configured (see VISION_PROVIDER in backend/.env.example).",
                )
            await emit(Stage.thinking, "Working out the answer")
            ocr_prompt = ocr.text if ocr else ""
            if sign_en:
                ocr_prompt += f"\n(English translation: {sign_en})"
            t0 = time.perf_counter()
            try:
                async with asyncio.timeout(s.vision_timeout_s):
                    vision = await svc.vision.answer(
                        inp.image, q_en, intent, inp.profile, ocr_prompt,
                        maps.as_prompt() if maps else "",
                    )
            except (TimeoutError, VisionError, httpx.HTTPError) as e:
                r.errors["vision"] = "refusal" if isinstance(e, VisionRefusal) else type(e).__name__
                log.warning("vision failed: %r", e)
                return response(
                    Status.error, intent=intent, transcript=transcript, help=help_offer,
                    error="I couldn't work out an answer right now. Please try again.",
                )
            finally:
                r.timings["vision"] = round((time.perf_counter() - t0) * 1000)

            # ---- 6. Fuse evidence, enforce safety, shape for the profile ----------
            await emit(Stage.checking, "Checking the answer")
            fused = evidence_fusion.fuse(vision, ocr, meta.frame_quality, maps)
            for name in r.errors:
                fused.confidence.reasons.append(f"{name}_unavailable")
            if maps:
                fused.grounding.append(maps.as_prompt())
            checked = validator.validate(vision, intent, fused.confidence.score, fused.grounding)
            if checked.issues:
                log.info("validator issues: %s", checked.issues)

            if checked.force_retake:
                return await _retake(
                    svc, r, response, inp, out_lang, checked.answer, intent, fused.confidence,
                    checked.issues, transcript, fused.sign_text, maps, help_offer,
                )

            if intent not in (Intent.traffic_signal, Intent.navigation, Intent.emergency):
                # Models (small ones especially) tack crossing warnings onto every answer;
                # keep cautions where they carry safety meaning.
                checked.answer.caution = ""
            shaped = _shape_for_profile(checked.answer, inp.profile)

            # ---- 7. Translate the answer back and speak it ------------------------
            answer, ans_lang = await _localize(svc, r, shaped, out_lang)
            if checked.use_traffic_caution:
                answer.caution = policies.TRAFFIC_CAUTION[ans_lang]
            spoken = _spoken_text(answer, intent)
            await emit(Stage.speaking, "Preparing speech")
            audio = await _speak(svc, r, spoken, ans_lang, inp.profile, meta.include_audio)
            return response(
                Status.ok,
                language=ans_lang,
                intent=intent,
                answer=answer,
                spoken_text=spoken,
                transcript=transcript,
                sign_text=fused.sign_text or None,
                confidence=fused.confidence,
                landmarks=maps.landmarks[:6] if maps else [],
                bus_routes=maps.bus_routes[:10] if maps else [],
                help=help_offer,
                raw_answer=vision.plain_reply or None,
                **audio,
            )
    except TimeoutError:
        log.warning("request %s hit the overall deadline", meta.request_id)
        msg = {
            Language.en: "This is taking too long. Please check your connection and try again.",
            Language.hi: "बहुत देर हो रही है। कृपया कनेक्शन जाँचें और फिर कोशिश करें।",
            Language.te: "చాలా సమయం పడుతోంది. దయచేసి కనెక్షన్ చూసి మళ్లీ ప్రయత్నించండి.",
        }[out_lang]
        return response(Status.error, spoken_text=msg, error="deadline_exceeded")
    finally:
        await emit(Stage.done, "Done")


def _shape_for_profile(a: VisionAnswer, profile: Profile) -> Answer:
    """Accessibility adapter: rewrite the validated answer to suit the user's condition.

    The model already wrote for the profile (vision.PROFILE_RULES); this enforces
    the structural guarantees regardless of what the model returned.
    """
    steps, details = list(a.steps), list(a.details)
    if profile == Profile.ageing:
        steps = steps[:4]  # one instruction at a time, never a long list
    elif profile == Profile.hearing:
        details = details[:3]  # captions: keep the screen calm
    elif profile == Profile.visual:
        details = details[:5]  # offered on request, not read out unprompted
    return Answer(
        short=a.short,
        steps=steps,
        details=details,
        simpler=a.simpler or None,
        follow_up=a.follow_up or None,
        caution=a.caution or None,
    )


async def _localize(svc: Services, r: _Run, ans: Answer, lang: Language) -> tuple[Answer, Language]:
    """Translate the English answer. Returns the language actually delivered: if NMT
    is unavailable the answer stays English and is labelled so, so the client and
    TalkBack pick an English voice instead of reading English with a Telugu one."""
    if lang == Language.en:
        return ans, lang
    if not svc.bhashini.configured:
        return ans, Language.en
    fields = [ans.short, ans.simpler or "", ans.follow_up or "", ans.caution or ""]
    texts = fields + ans.steps + ans.details
    translated = await r.soft(
        "nmt_out", svc.bhashini.translate_many(texts, Language.en, lang), svc.settings.nmt_timeout_s
    )
    if translated is None:
        return ans, Language.en  # better an English answer than none
    short, simpler, follow_up, caution = translated[:4]
    n_steps = len(ans.steps)
    return Answer(
        short=short,
        simpler=simpler or None,
        follow_up=follow_up or None,
        caution=caution or None,
        steps=translated[4 : 4 + n_steps],
        details=translated[4 + n_steps :],
    ), lang


def _spoken_text(a: Answer, intent: Intent) -> str:
    """Answer first, then any safety caution, then the offer of more."""
    parts = [a.short]
    if a.steps and intent in (Intent.navigation, Intent.emergency):
        parts.append(a.steps[0])
    if a.caution:
        parts.append(a.caution)
    if a.follow_up:
        parts.append(a.follow_up)
    return " ".join(p for p in parts if p)


async def _speak(
    svc: Services, r: _Run, text: str, lang: Language, profile: Profile, wanted: bool
) -> dict:
    """TTS via Bhashini. Skipped for the hearing profile (captions only)."""
    if not wanted or profile == Profile.hearing or not svc.bhashini.configured or not text:
        return {}
    result = await r.soft("tts", svc.bhashini.tts(text, lang), svc.settings.tts_timeout_s)
    if not result:
        return {}
    audio_b64, mime = result
    return {"audio_b64": audio_b64, "audio_mime": mime}


async def _retake(
    svc: Services,
    r: _Run,
    response: Callable[..., AnalyzeResponse],
    inp: PipelineInput,
    lang: Language,
    a: VisionAnswer,
    intent: Intent,
    confidence: ConfidenceReport,
    issues: list[str],
    transcript: str | None,
    sign_text: str,
    maps: MapContext | None,
    help_offer,
) -> AnalyzeResponse:
    """Say what was read, what is missing, and how to retake - never a silent guess."""
    unverified = any(i.startswith("unverified_routes") for i in issues)
    # The model's own words (English) are only used if they can be translated;
    # otherwise the whole reply switches to English so it isn't half one language.
    said_en = None if unverified else (a.short or None)  # unverified: discard its wording
    hint_en = a.retake_hint or None
    to_translate = [t for t in (said_en, hint_en) if t]
    translated: list[str] | None = to_translate
    if to_translate and lang != Language.en:
        translated = None
        if svc.bhashini.configured:
            translated = await r.soft(
                "nmt_out", svc.bhashini.translate_many(to_translate, Language.en, lang),
                svc.settings.nmt_timeout_s,
            )
        if translated is None:
            lang, translated = Language.en, to_translate
    it = iter(translated)
    said = next(it) if said_en else (policies.UNVERIFIED_ROUTE_REPLY[lang] if unverified else None)
    hint = next(it) if hint_en else policies.GENERIC_RETAKE_HINT[lang]

    if confidence.level == ConfidenceLevel.low and help_offer is None:
        loc = inp.meta.location
        help_offer = svc.helpdesk.offer(
            "low_confidence", lang, loc.lat if loc else None, loc.lon if loc else None
        )
    spoken = " ".join(p for p in (said, hint) if p)
    audio = await _speak(svc, r, spoken, lang, inp.profile, inp.meta.include_audio)
    return response(
        Status.needs_retake,
        language=lang,
        intent=intent,
        answer=Answer(short=said or hint),
        spoken_text=spoken,
        retake_hint=hint,
        transcript=transcript,
        sign_text=sign_text or None,
        confidence=confidence,
        landmarks=maps.landmarks[:6] if maps else [],
        help=help_offer,
        raw_answer=a.plain_reply or None,
        **audio,
    )
