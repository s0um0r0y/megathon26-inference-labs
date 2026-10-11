"""Pipeline and API tests with fake providers (no network)."""

import asyncio
import json
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from config import Settings
from orchestration import pipeline
from schemas.request import AnalyzeMetadata, Language, Location, Profile
from schemas.response import BusRoute, Status
from services.bhashini import AsrResult
from services.human_help import HelpDesk
from services.maps import MapContext
from services.ocr import OcrResult
from services.vision import VisionAnswer

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


@dataclass
class FakeBhashini:
    configured: bool = True
    asr_text: str = "బస్ 219 ఎక్కడికి వెళ్తుంది"
    asr_conf: float = 0.85
    calls: list = field(default_factory=list)

    async def asr(self, wav_b64, lang):
        self.calls.append(("asr", lang))
        return AsrResult(self.asr_text, self.asr_conf)

    async def translate(self, text, src, tgt):
        self.calls.append(("nmt", src, tgt))
        return f"[{tgt}]{text}" if tgt != Language.en else "Where does bus 219 go?"

    async def translate_many(self, texts, src, tgt):
        return [await self.translate(t, src, tgt) if t else "" for t in texts]

    async def tts(self, text, lang):
        self.calls.append(("tts", lang))
        return "UklGRg==", "audio/wav"


@dataclass
class FakeVision:
    answer_: VisionAnswer
    configured: bool = True
    delay: float = 0.0
    seen: dict = field(default_factory=dict)

    async def answer(self, image, question_en, intent, profile, ocr_text, map_context):
        self.seen.update(question=question_en, intent=intent, profile=profile, ocr=ocr_text, maps=map_context)
        await asyncio.sleep(self.delay)
        return self.answer_


@dataclass
class FakeOcr:
    result: OcrResult

    async def read(self, image):
        return self.result


@dataclass
class FakeMaps:
    ctx: MapContext | None = None
    fail: bool = False

    async def context(self, loc):
        if self.fail:
            raise httpx.ConnectError("overpass down")
        return self.ctx


def bus_answer(**kw) -> VisionAnswer:
    base = dict(
        answerable=True,
        short="Bus 219 goes to Secunderabad station; it is the third route listed.",
        simpler="Bus 219 goes to the station.",
        follow_up="Do you want the other routes?",
        details=["10H goes to Koti."],
        sign_text="10H Koti\n5K Mehdipatnam\n219 Secunderabad",
        sign_type="bus_board",
        confidence=0.9,
        plain_reply="The board lists routes 10H, 5K and 219...",
    )
    base.update(kw)
    return VisionAnswer(**base)


def make_services(vision: VisionAnswer | None = None, **over) -> pipeline.Services:
    s = Settings(_env_file=None)
    return pipeline.Services(
        settings=over.pop("settings", s),
        http=None,  # type: ignore[arg-type]
        bhashini=over.pop("bhashini", FakeBhashini()),
        vision=over.pop("vision_client", FakeVision(vision or bus_answer())),
        ocr=over.pop("ocr", FakeOcr(OcrResult("10H Koti\n5K Mehdipatnam\n219 Secunderabad", 0.9, "fake"))),
        maps=over.pop("maps", FakeMaps()),
        helpdesk=HelpDesk(),
    )


def inp(**meta_kw) -> pipeline.PipelineInput:
    audio = meta_kw.pop("audio", b"RIFFfake")
    lang = meta_kw.pop("language", Language.te)
    profile = meta_kw.pop("profile", Profile.visual)
    meta = AnalyzeMetadata(session_id="s", request_id="req-1", **meta_kw)
    return pipeline.PipelineInput(meta=meta, image=JPEG, audio_wav=audio, language=lang, profile=profile)


async def test_happy_path_speech_to_speech():
    svc = make_services()
    stages = []

    async def emit(stage, msg):
        stages.append(stage)

    res = await pipeline.run(svc, inp(), emit)
    assert res.status == Status.ok
    assert res.intent == "bus_route"
    assert res.language == Language.te
    assert res.answer.short.startswith("[te]Bus 219")
    assert res.audio_b64 and res.audio_mime == "audio/wav"
    assert res.confidence.level == "high"
    assert res.raw_answer
    assert stages[-1] == "done" and "thinking" in stages
    assert svc.vision.seen["question"] == "Where does bus 219 go?"


async def test_unsure_transcript_asks_for_confirmation_before_acting():
    svc = make_services(bhashini=FakeBhashini(asr_text="bus", asr_conf=0.4))
    res = await pipeline.run(svc, inp())
    assert res.status == Status.needs_confirmation
    assert res.transcript == "bus"
    assert "bus" in res.spoken_text
    assert svc.vision.seen == {}  # never reached the model


async def test_confirmed_request_skips_asr():
    bh = FakeBhashini(asr_conf=0.1)
    svc = make_services(bhashini=bh)
    res = await pipeline.run(svc, inp(confirmed=True, query_text="బస్ 219 ఎక్కడికి"))
    assert res.status == Status.ok
    assert not any(c[0] == "asr" for c in bh.calls)


async def test_guessed_route_becomes_retake_not_answer():
    svc = make_services(bus_answer(short="Take bus 21 to the station.", sign_text="219 Secunderabad"),
                        ocr=FakeOcr(OcrResult("219 Secunderabad", 0.9, "fake")))
    res = await pipeline.run(svc, inp(language=Language.en, audio=None, query_text="Which bus goes to the station?"))
    assert res.status == Status.needs_retake
    assert "21 " not in res.spoken_text
    assert "won't guess" in res.spoken_text


async def test_unreadable_photo_guides_retake_and_offers_help():
    a = bus_answer(answerable=False, short="I can see a bus board but the route numbers are cut off.",
                   retake_hint="Tilt the phone up, the top of the board is cut off.", confidence=0.3, sign_text="")
    svc = make_services(a, ocr=FakeOcr(OcrResult("", 0.1, "fake")))
    res = await pipeline.run(svc, inp(language=Language.en, audio=None, query_text="Which bus goes to Koti?"))
    assert res.status == Status.needs_retake
    assert res.retake_hint == "Tilt the phone up, the top of the board is cut off."
    assert "cut off" in res.spoken_text
    assert res.help is not None and res.help.call_number == "112"


async def test_signal_answer_always_has_caution_in_user_language():
    a = VisionAnswer(answerable=True, short="The signal shows a green walking man. You can cross now.",
                     sign_type="traffic_signal", confidence=0.9, sign_text="")
    svc = make_services(a, ocr=FakeOcr(OcrResult("", 0.0, "none")))
    res = await pipeline.run(svc, inp(language=Language.hi, audio=None, query_text="सिग्नल क्या दिखा रहा है?"))
    assert res.status == Status.ok
    assert "cross now" not in res.answer.short.lower()
    assert res.answer.caution and "ट्रैफ़िक" in res.answer.caution
    assert res.answer.caution in res.spoken_text


async def test_out_of_scope_never_calls_model():
    vision = FakeVision(bus_answer())
    svc = make_services(vision_client=vision, bhashini=FakeBhashini(configured=False))
    res = await pipeline.run(svc, inp(language=Language.en, audio=None, query_text="Which medicine should I take?"))
    assert res.intent == "out_of_scope"
    assert vision.seen == {}


async def test_maps_failure_degrades_softly():
    svc = make_services(maps=FakeMaps(fail=True))
    res = await pipeline.run(svc, inp(location=Location(lat=17.43, lon=78.5)))
    assert res.status == Status.ok
    assert "maps" in res.timings_ms
    assert "maps_unavailable" in res.confidence.reasons


async def test_map_routes_ground_bus_answers():
    a = bus_answer(short="Bus 47L stops here and goes to Charminar.", sign_text="")
    ctx = MapContext(bus_routes=[BusRoute(ref="47L", to="Charminar")])
    svc = make_services(a, ocr=FakeOcr(OcrResult("", 0.0, "none")), maps=FakeMaps(ctx=ctx))
    res = await pipeline.run(svc, inp(language=Language.en, audio=None, query_text="Which bus goes to Charminar?",
                                      location=Location(lat=17.36, lon=78.47)))
    assert res.status == Status.ok, res


async def test_hearing_profile_gets_no_tts():
    bh = FakeBhashini()
    svc = make_services(bhashini=bh)
    res = await pipeline.run(svc, inp(profile=Profile.hearing))
    assert res.status == Status.ok and res.audio_b64 is None
    assert not any(c[0] == "tts" for c in bh.calls)


async def test_overall_deadline():
    s = Settings(_env_file=None, request_deadline_s=0.2, vision_timeout_s=5)
    svc = make_services(settings=s, vision_client=FakeVision(bus_answer(), delay=2))
    res = await pipeline.run(svc, inp(language=Language.en, audio=None, query_text="Which bus?"))
    assert res.status == Status.error and res.error == "deadline_exceeded"


# ---- API: sessions, analyze, websocket cancellation --------------------------------


@pytest.fixture
def client(monkeypatch):
    import main

    with TestClient(main.app) as c:
        main.app.state.services = make_services(vision_client=FakeVision(bus_answer(), delay=1.0))
        yield c


def _post_analyze(client, session_id, request_id, **meta):
    return client.post(
        "/api/analyze",
        data={"metadata": json.dumps({"session_id": session_id, "request_id": request_id, **meta})},
        files={"image": ("frame.jpg", JPEG, "image/jpeg")},
    )


def test_session_lifecycle(client):
    sid = client.post("/api/sessions", json={"language": "te", "profile": "ageing"}).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}").json()["profile"] == "ageing"
    assert client.patch(f"/api/sessions/{sid}", json={"profile": "visual"}).json()["profile"] == "visual"
    assert client.get("/api/sessions/nope").status_code == 404


def test_analyze_endpoint_and_progress_events(client):
    sid = client.post("/api/sessions", json={"language": "en"}).json()["session_id"]
    with client.websocket_connect(f"/ws/{sid}") as ws:
        res = _post_analyze(client, sid, "req-a", query_text="Which bus goes to Secunderabad?")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "ok"
        stages = []
        while True:
            ev = ws.receive_json()
            stages.append(ev["stage"])
            if ev["stage"] == "done":
                break
    assert "thinking" in stages


def test_cancel_over_websocket(client):
    import threading

    sid = client.post("/api/sessions", json={"language": "en"}).json()["session_id"]
    result = {}

    def call():
        result["res"] = _post_analyze(client, sid, "req-c", query_text="Which bus?").json()

    with client.websocket_connect(f"/ws/{sid}") as ws:
        t = threading.Thread(target=call)
        t.start()
        # Wait until the model step starts, then cancel.
        while ws.receive_json().get("stage") != "thinking":
            pass
        ws.send_json({"type": "cancel", "request_id": "req-c"})
        t.join(timeout=5)
    assert result["res"]["status"] == "cancelled"


def test_rejects_non_jpeg(client):
    sid = client.post("/api/sessions", json={}).json()["session_id"]
    res = client.post(
        "/api/analyze",
        data={"metadata": json.dumps({"session_id": sid, "request_id": "req-x"})},
        files={"image": ("x.png", b"png", "image/png")},
    )
    assert res.status_code == 415


async def test_untranslatable_answer_is_labelled_english():
    svc = make_services(bhashini=FakeBhashini(configured=False))
    res = await pipeline.run(svc, inp(language=Language.te, audio=None, query_text="Which bus?"))
    assert res.status == Status.ok
    assert res.language == Language.en
    assert res.answer.short.startswith("Bus 219")


async def test_untranslatable_retake_is_one_language():
    a = bus_answer(answerable=False, short="The route numbers are cut off.",
                   retake_hint="Move the phone up.", confidence=0.3, sign_text="")
    svc = make_services(a, ocr=FakeOcr(OcrResult("", 0.1, "fake")), bhashini=FakeBhashini(configured=False))
    res = await pipeline.run(svc, inp(language=Language.hi, audio=None, query_text="Which bus?"))
    assert res.status == Status.needs_retake
    assert res.language == Language.en
    assert res.spoken_text == "The route numbers are cut off. Move the phone up."
