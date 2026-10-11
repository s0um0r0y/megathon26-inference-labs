# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Backend (Python 3.11+ via uv; the system python is 3.9, and a ROS install on `PYTHONPATH` breaks pytest, so unset it):

```bash
cd backend
uv sync
env -u PYTHONPATH uv run uvicorn main:app --reload --port 8000
env -u PYTHONPATH uv run pytest -q                                  # all tests
env -u PYTHONPATH uv run pytest -q tests/test_safety.py -k crossing  # one test
```

Keys go in `backend/.env` (see `.env.example`). Missing providers degrade instead of crashing; `GET /api/health` shows which are configured.

Frontend: static PWA in `frontend/` (`index.html` holds the markup, styles and logic; no build step). FastAPI serves it at `/`, so run the backend over HTTPS for phone testing:

```bash
cd backend
uv run uvicorn main:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs/dev.key --ssl-certfile certs/dev.crt
```

`backend/uv.toml` holds the uv settings (managed Python 3.12 only). While it exists, uv ignores `[tool.uv]` in `pyproject.toml`, except project fields like `package`, which must stay there.

## Architecture

- Request flow (PWA): `frontend/index.html` posts multipart `POST /api/ask` (image, query, lang, profile) and gets flat JSON `{answer, simple, more, read_text, confidence, needs_retake, retake_hint, lang, audio_b64?, raw_answer}`. The contract is in `frontend/README.md`, and the mapping is `to_pwa()` in `backend/api/ask.py`. Safety cautions are folded into `answer`/`simple` because those are the strings the app speaks. `POST /api/tts` returns Bhashini audio for any other text the app speaks (204 means the browser voice is used). The app finds the backend by calling `api/health` on its own origin. Sample signs run entirely in the browser.
- `POST /api/analyze` + `WS /ws/{session_id}` (sessions, progress events, cancellation) remain for a richer client; `/api/ask` is the stateless equivalent.
- `backend/orchestration/pipeline.py` runs: ASR + OCR + maps in parallel (TaskGroup) → confirm the transcript if ASR is unsure → NMT to English → `intent_router` (deterministic keyword rules) → `services/vision.py` (Claude or an open model behind any OpenAI-compatible server, selected by `VISION_PROVIDER`; JSON output normalised by `_coerce_answer`) → `evidence_fusion` → `safety/validator` → profile shaping → NMT back → Bhashini TTS. Each external call goes through `_Run.soft()`, which applies its own `asyncio.timeout` and returns None on failure. One overall deadline wraps the whole request. Don't catch `CancelledError` in steps.
- Safety rules live in `safety/policies.py` (regexes + pre-translated en/hi/te texts) and are applied in `safety/validator.py` to the English answer *before* translation. Table-driven cases are in `backend/tests/cases/*.json`. Statuses `needs_retake` and `needs_confirmation` are how "no silent guesses" reaches the client.
- Language services come from the IIIT Bhashini sandbox (`LANGUAGE_PROVIDER=canvas`, `CanvasClient` in `services/bhashini.py`): one `access-token` header, one model ID per service and language pair (`CANVAS_*_MODEL`). Request shapes are from `https://canvas.iiit.ac.in/sandboxbeprod/openapi.json`. Responses are `{status, message, data}` with HTTP 200 even on errors. NMT returns `data.output_text`, TTS returns `data.s3_url` (a WAV to download), and an NMT output of `"........"` means the model is for a different language pair. `UlcaClient` is the public-Bhashini alternative.
- If NMT is unavailable, the response `language` is `en` (never English text labelled `te`/`hi`), so TalkBack and TTS pick the right voice.
- Open models via Ollama: use `OPENAI_JSON_MODE=json_object` (grammar-constrained `json_schema` makes qwen2.5vl loop until the server aborts). Photos are downscaled to `VISION_MAX_SIDE`, and vision HTTP calls use `VISION_TIMEOUT_S` per request, not the shared client's default. qwen2.5vl:7b on the 6 GB RTX 3060 runs about a third on the CPU and takes 12–30 s per answer.

## Project: SignSaathi

SignSaathi is an accessibility layer that sits between a user and a general-purpose vision LLM. The user points a phone at a street sign, bus board, shop board or pedestrian signal and asks a question in English, Hindi or Telugu. The app replies with a short answer that focuses on the task and is adapted to the user's condition:

- **Visual** (mandatory): voice-first, camera framing cues, answers that give distance and direction.
- **Hearing**: live captions, transcription and translation of announcements, vibration and flash alerts.
- **Ageing**: large text, high contrast, slower TTS, one step at a time, "Explain simpler" and "Repeat" buttons.

The app infers the condition from interaction signals and then asks the user to confirm it. The user can always override the inferred profile.

### Pipeline (from the M1 doc)

1. Input: voice, a camera photo, or tap/type/phrase board
2. Bhashini ASR, plus OCR on the sign (with confidence scores)
3. Bhashini NMT translates the query and the sign text into English
4. Reasoning engine: a vision-capable LLM, plus GPS/OpenStreetMap and a bus route lookup, returns a structured answer
5. **Accessibility adapter**, the core contribution: rewrites the raw answer for the user's profile (short, simple or stepwise) and applies the safety and failure rules
6. Bhashini NMT translates the answer from English back into the user's language
7. Output: Bhashini TTS (speed adjustable) and/or visual output (captions, alerts, vibration)
8. Feedback loop: confirm or repeat, retake-photo cues, Explain simpler

All language steps (ASR, NMT, TTS) go through the Bhashini Sandbox APIs.

### Stack

- Frontend: a PWA for Android Chrome and laptop that uses the camera, mic, vibration and geolocation APIs. The markup must work with TalkBack: real headings, labelled buttons and lists.
- Backend: a Python FastAPI orchestration service that handles the pipeline, the condition profile and the failure logic.
- Offline fallback: Google ML Kit for on-device OCR, plus cached TTS prompts.
- All external resources must be declared (a hackathon rule).

### Behavioural rules the implementation must keep

- Give the answer first in one sentence, then offer more ("Want the next two buses?"). Never read out a whole board or table.
- **Never declare it safe to cross.** Signal readings are informational only and always end with a caution. Give no medical, legal or financial advice.
- **No silent guesses.** On low OCR or ASR confidence, say what was read and what is missing, and guide a retake or ask for confirmation.
- Keep a side-by-side view of the raw assistant reply and the SignSaathi reply, for testing and the demo.

### Testing plan

- About 50 photos of real Hyderabad signs: measure OCR accuracy, ASR WER per language, and translation quality rated by native speakers.
- Scripted end-to-end tasks for each condition.
- Accessibility runs with TalkBack only, with audio muted, and at large text; automated checks with Lighthouse and axe.
- Raw vs SignSaathi comparisons.
- Robustness runs with blurred or tilted photos, street noise, and throttled or dropped network.
