"""IIIT Canvas sandbox client against a mock server (no network).

Response shapes for NMT, TTS and errors mirror what the live sandbox returned;
ASR/OCR shapes are not documented, so those tests cover the tolerant parser.
"""

import json

import httpx
import pytest

from config import Settings
from schemas.request import Language
from services.bhashini import BhashiniError, CanvasClient, _find_text

BASE = "https://canvas.example/sandboxbeprod"


def ok(data):
    return httpx.Response(200, json={"status": "success", "message": "ok", "data": data, "code": 200})


def err(message, code=400):
    return httpx.Response(200, json={"status": "error", "message": message, "data": None, "code": code})


def make(handler, **kw):
    seen = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    s = Settings(_env_file=None, canvas_base_url=BASE, **kw)
    return CanvasClient(httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), s), seen


async def test_nmt_batches_and_sends_token():
    def handler(req):
        body = json.loads(req.content)
        return ok({"output_text": [f"hi:{t}" for t in body["input_text"]]})

    c, seen = make(handler, canvas_access_token="tok", canvas_nmt_en_hi_model="m-en-hi")
    out = await c.translate_many(["Bus 219.", "", "Next stop."], Language.en, Language.hi)
    assert out == ["hi:Bus 219.", "", "hi:Next stop."]
    assert len(seen) == 1  # one batched call, empty strings skipped
    assert str(seen[0].url) == f"{BASE}/check_model_status_and_infer/m-en-hi"
    assert seen[0].headers["access-token"] == "tok"


async def test_wrong_direction_model_is_an_error_not_dots():
    c, _ = make(lambda req: ok({"output_text": ["........"]}),
                canvas_access_token="tok", canvas_nmt_hi_en_model="actually-en-hi")
    with pytest.raises(BhashiniError, match="wrong model"):
        await c.translate("यह बस", Language.hi, Language.en)


async def test_missing_model_or_token():
    c, _ = make(lambda req: ok({}), canvas_access_token="tok")
    with pytest.raises(BhashiniError, match="no Canvas model"):
        await c.translate("x", Language.te, Language.en)
    c, _ = make(lambda req: ok({}), canvas_nmt_en_hi_model="m")
    assert not c.configured
    with pytest.raises(BhashiniError, match="access token"):
        await c.translate("x", Language.en, Language.hi)


async def test_service_error_is_raised():
    c, _ = make(lambda req: err("Tryout limit exceeded", 429),
                canvas_access_token="tok", canvas_nmt_en_hi_model="m")
    with pytest.raises(BhashiniError, match="Tryout limit"):
        await c.translate("x", Language.en, Language.hi)


async def test_relogin_on_expired_token():
    tokens = []

    def handler(req):
        if req.url.path.endswith("/login"):
            assert json.loads(req.content) == {"email": "me@example.org", "password": "pw"}
            return httpx.Response(200, json={"status": "success", "data": {"access_token": "fresh"}})
        tokens.append(req.headers.get("access-token"))
        if req.headers.get("access-token") != "fresh":
            return err("Invalid or expired access token", 401)
        return ok({"output_text": ["अगला स्टॉप"]})

    c, _ = make(handler, canvas_access_token="stale", canvas_email="me@example.org",
                canvas_password="pw", canvas_nmt_en_hi_model="m")
    assert await c.translate("Next stop", Language.en, Language.hi) == "अगला स्टॉप"
    assert tokens == ["stale", "fresh"]


async def test_tts_downloads_audio_url():
    def handler(req):
        if req.url.host == "audio.example":
            return httpx.Response(200, content=b"RIFFwav", headers={"content-type": "audio/wav"})
        assert json.loads(req.content) == {"text": "नमस्ते", "gender": "female"}
        return ok({"s3_url": "https://audio.example/out.wav"})

    c, _ = make(handler, canvas_access_token="tok", canvas_tts_hi_model="m-tts")
    audio_b64, mime = await c.tts("नमस्ते", Language.hi)
    assert audio_b64 == "UklGRndhdg==" and mime == "audio/wav"


async def test_asr_and_ocr_multipart():
    def handler(req):
        assert b'name="audio_file"' in req.content or b'name="file"' in req.content
        if "infer_asr" in req.url.path:
            return ok({"transcript": "बस 219 कहाँ जाती है"})
        return ok({"result": [{"text": "219 सिकंदराबाद"}, {"text": "10H कोटी"}]})

    c, _ = make(handler, canvas_access_token="tok", canvas_asr_hi_model="a", canvas_ocr_model="o")
    asr = await c.asr("UklGRg==", Language.hi)
    assert asr.text == "बस 219 कहाँ जाती है" and asr.confidence > 0.6
    assert await c.ocr(b"jpeg") == "219 सिकंदराबाद\n10H कोटी"


def test_find_text_shapes():
    assert _find_text({"output_text": "a"}) == "a"
    assert _find_text({"data": {"lines": ["a", "b"]}}) == "a\nb"
    assert _find_text({"n": 1}) is None


def test_health_services():
    c, _ = make(lambda req: ok({}), canvas_access_token="t", canvas_nmt_en_hi_model="m", canvas_ocr_model="o")
    s = c.services()
    assert s["nmt_en_hi"] and s["ocr"] and not s["nmt_hi_en"] and not s["asr_hi"]
    assert c.configured
