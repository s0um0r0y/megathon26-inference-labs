"""/api/ask and /api/tts (the static PWA's contract) and static serving."""

import io

import pytest
from fastapi.testclient import TestClient

from services.vision import VisionAnswer
from tests.test_pipeline import FakeBhashini, FakeOcr, FakeVision, bus_answer, make_services
from services.ocr import OcrResult


@pytest.fixture
def app_with():
    import main

    def make(**kw):
        client = TestClient(main.app)
        client.__enter__()
        main.app.state.services = make_services(**kw)
        return client

    clients = []
    yield lambda **kw: clients.append(make(**kw)) or clients[-1]
    for c in clients:
        c.__exit__(None, None, None)


def post(client, query="Which bus goes to Secunderabad?", lang="en", profile="visual", image=b"\xff\xd8\xffjpeg"):
    return client.post(
        "/api/ask",
        data={"query": query, "lang": lang, "profile": profile},
        files={"image": ("sign.jpg", image, "image/jpeg")},
    )


def test_answer_shape_and_audio(app_with):
    c = app_with()
    j = post(c).json()
    assert j["needs_retake"] is False
    assert j["answer"].startswith("Bus 219 goes to Secunderabad")
    assert j["simple"] == "Bus 219 goes to the station."
    assert "10H goes to Koti." in j["more"]
    assert j["read_text"].startswith("10H Koti")
    assert j["confidence"] == "high" and j["lang"] == "en"
    assert j["audio_b64"] and j["audio_text"] == j["answer"]
    assert j["raw_answer"]


def test_signal_caution_is_spoken(app_with):
    a = VisionAnswer(answerable=True, short="The signal shows a red standing man.",
                     sign_type="traffic_signal", confidence=0.9)
    c = app_with(vision_client=FakeVision(a), ocr=FakeOcr(OcrResult("", 0.0, "none")))
    j = post(c, query="What is the signal showing?", profile="ageing").json()
    assert "Listen for traffic" in j["answer"] and "Listen for traffic" in j["simple"]
    assert j["audio_text"] == j["simple"]  # older adults hear the simple version first


def test_retake_shape(app_with):
    a = bus_answer(answerable=False, short="The route numbers are cut off.",
                   retake_hint="Move the phone up.", confidence=0.3, sign_text="")
    c = app_with(vision_client=FakeVision(a), ocr=FakeOcr(OcrResult("", 0.1, "fake")))
    j = post(c).json()
    assert j["needs_retake"] is True
    assert j["retake_hint"] == "The route numbers are cut off. Move the phone up."


def test_hearing_profile_gets_no_audio(app_with):
    c = app_with()
    assert "audio_b64" not in post(c, profile="hearing").json()


def test_pipeline_error_is_503(app_with):
    c = app_with(vision_client=FakeVision(bus_answer(), configured=False))
    assert post(c).status_code == 503


def test_png_upload_is_converted(app_with):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    vision = FakeVision(bus_answer())
    c = app_with(vision_client=vision)
    assert post(c, image=buf.getvalue()).status_code == 200


def test_tts_endpoint(app_with):
    c = app_with()
    r = c.post("/api/tts", data={"text": "नमस्ते", "lang": "hi"})
    assert r.status_code == 200 and r.json()["audio_b64"]
    c2 = app_with(bhashini=FakeBhashini(configured=False))
    assert c2.post("/api/tts", data={"text": "hi", "lang": "en"}).status_code == 204


def test_frontend_served_at_root(app_with):
    c = app_with()
    r = c.get("/")
    assert r.status_code == 200 and "SignSaathi" in r.text
    assert c.get("/sw.js").status_code == 200
    assert c.get("/api/health").json()["ok"] is True
