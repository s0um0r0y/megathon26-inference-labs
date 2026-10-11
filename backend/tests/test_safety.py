import json
from pathlib import Path

import pytest

from orchestration import intent_router
from safety import confidence, validator
from schemas.request import FrameQuality
from schemas.response import ConfidenceLevel, Intent
from services.vision import VisionAnswer

CASES = sorted((Path(__file__).parent / "cases").glob("*.json"))


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_validator_cases(path: Path):
    case = json.loads(path.read_text())
    answer = VisionAnswer(**case["answer"])
    v = validator.validate(answer, Intent(case["intent"]), case["confidence"], case["evidence"])
    exp = case["expect"]
    for key in ("force_retake", "use_traffic_caution"):
        if key in exp:
            assert getattr(v, key) == exp[key], case["description"]
    for key in ("short", "simpler", "steps", "details"):
        if key in exp:
            assert getattr(v.answer, key) == exp[key], case["description"]
    for issue in exp.get("issues_include", []):
        assert issue in v.issues, f"{case['description']}: missing {issue} in {v.issues}"
    if exp.get("issues_include") == []:
        assert v.issues == []


@pytest.mark.parametrize(
    "text",
    [
        "It is safe to cross.",
        "You can cross the road now.",
        "Go ahead.",
        "No cars are coming.",
        "The road is clear.",
    ],
)
def test_crossing_language_always_flagged(text):
    assert validator._is_unsafe_crossing(text)


@pytest.mark.parametrize(
    "text",
    ["The signal shows a red standing man.", "The green walking man is lit.", "The light is amber."],
)
def test_signal_descriptions_not_flagged(text):
    assert not validator._is_unsafe_crossing(text)


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Which bus goes to Secunderabad?", Intent.bus_route),
        ("Is this shop open?", Intent.shop_info),
        ("Is the pharmacy open now?", Intent.shop_info),
        ("What is the signal showing?", Intent.traffic_signal),
        ("Can I cross?", Intent.traffic_signal),
        ("Where is the nearest bus stop?", Intent.bus_route),
        ("Where is the hospital?", Intent.navigation),
        ("There's been an accident, help me", Intent.emergency),
        ("Which medicine should I take for fever?", Intent.out_of_scope),
        ("Should I invest in shares?", Intent.out_of_scope),
        ("What does this say?", Intent.read_sign),
        ("", Intent.read_sign),
    ],
)
def test_intent_routing(question, intent):
    assert intent_router.route(question) == intent


def test_empty_question_on_signal_photo_routes_to_signal():
    assert intent_router.route("", "PEDESTRIAN CROSSING") == Intent.traffic_signal


def test_asr_confidence_heuristic():
    assert confidence.asr_confidence("") == 0.0
    assert confidence.asr_confidence("bus") < confidence.ASR_CONFIRM_BELOW
    assert confidence.asr_confidence("which bus goes to the station") >= confidence.ASR_CONFIRM_BELOW
    assert confidence.asr_confidence("the the the the the the") < confidence.ASR_CONFIRM_BELOW


def test_dark_blurry_frame_caps_confidence():
    dark = FrameQuality(brightness=20, blur_score=10, motion=20, stable_frames=1)
    report = confidence.combine(
        {"vision": 0.95, "frame": confidence.frame_confidence(dark)}, []
    )
    assert report.level == ConfidenceLevel.low


def test_agreeing_readings_score_high():
    report = confidence.combine(
        {
            "vision": 0.9,
            "ocr": 0.9,
            "agreement": confidence.text_agreement("219 Secunderabad", "219 SECUNDERABAD"),
            "frame": 1.0,
        },
        [],
    )
    assert report.level == ConfidenceLevel.high


def test_route_token_does_not_match_substring():
    # "21" must not be considered grounded by "219".
    assert validator.unsupported_routes("Take bus 21.", ["219 Koti"]) == ["21"]
    assert validator.unsupported_routes("Take bus 219.", ["219 Koti"]) == []
    # Distances and timings are not routes.
    assert validator.unsupported_routes("The stop is 30 m ahead, open till 10 pm.", []) == []
