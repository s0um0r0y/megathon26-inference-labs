"""Vision client against a mocked OpenAI-compatible server (no network)."""

import json

import httpx
import pytest

from config import Settings
from schemas.request import Profile
from schemas.response import Intent
from services.vision import VisionClient, VisionError

GOOD = {
    "answerable": True,
    "short": "Bus 219 goes to Secunderabad.",
    "steps": [],
    "details": [],
    "simpler": "Bus 219 goes to the station.",
    "follow_up": "",
    "caution": "",
    "retake_hint": "",
    "sign_text": "219 Secunderabad",
    "sign_type": "bus_board",
    "confidence": "high",
    "plain_reply": "",
}


def settings(**kw) -> Settings:
    return Settings(
        _env_file=None,
        vision_provider="openai_compat",
        openai_base_url="http://llm.local/v1",
        openai_model="llama-vision",
        **kw,
    )


def client(handler, **kw) -> tuple[VisionClient, list[dict]]:
    seen: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"url": str(request.url), "headers": request.headers, "body": body})
        return handler(body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return VisionClient(http, settings(**kw)), seen


def completion(content: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]})


async def ask(vc: VisionClient):
    return await vc.answer(b"jpeg", "Which bus?", Intent.bus_route, Profile.visual, "219", "")


async def test_sends_image_and_json_object_by_default():
    vc, seen = client(lambda body: completion(json.dumps(GOOD)), openai_api_key="k")
    a = await ask(vc)
    assert a.answerable and a.short.startswith("Bus 219") and a.confidence == 0.9
    req = seen[0]
    assert req["url"] == "http://llm.local/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer k"
    user = req["body"]["messages"][1]["content"]
    assert user[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert req["body"]["response_format"]["type"] == "json_object"
    assert "Reply with only a JSON object" in req["body"]["messages"][0]["content"]


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(400, json={"error": "response_format json_schema not supported"}),
        httpx.Response(500, json={"error": {"message": "prediction aborted, token repeat limit reached"}}),
    ],
)
async def test_falls_back_to_json_object_when_schema_fails(failure):
    def handler(body):
        if body["response_format"]["type"] == "json_schema":
            return failure
        return completion(json.dumps(GOOD))

    vc, seen = client(handler, openai_json_mode="json_schema")
    assert (await ask(vc)).answerable
    assert [s["body"]["response_format"]["type"] for s in seen] == ["json_schema", "json_object"]
    assert "Reply with only a JSON object" in seen[1]["body"]["messages"][0]["content"]
    # Remembered: next call goes straight to json_object.
    await ask(vc)
    assert seen[2]["body"]["response_format"]["type"] == "json_object"


async def test_tolerates_fences_and_missing_fields():
    vc, _ = client(lambda body: completion('```json\n{"short": "Shop board.", "confidence": "HIGH", "steps": "one"}\n```'))
    a = await ask(vc)
    assert a.short == "Shop board."
    assert a.answerable is False  # missing -> unsure -> retake, never a guess
    assert a.steps == ["one"]
    assert a.sign_type == "other"


async def test_garbage_and_truncation_raise():
    vc, _ = client(lambda body: completion("I think it says bus 219"))
    with pytest.raises(VisionError):
        await ask(vc)
    vc, _ = client(lambda body: completion('{"short": "Bus', finish="length"))
    with pytest.raises(VisionError):
        await ask(vc)


async def test_configured_and_label():
    vc, _ = client(lambda body: completion("{}"))
    assert vc.configured and vc.label == "openai_compat:llama-vision"
    assert not VisionClient(None, Settings(_env_file=None, anthropic_api_key="")).configured  # type: ignore[arg-type]
