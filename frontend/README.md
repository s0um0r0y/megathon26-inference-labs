# SignSaathi frontend

Progressive web app for the SignSaathi pipeline. Plain HTML, CSS and JavaScript. No build step, no dependencies.

## Run

The backend serves this folder at `/` and the app connects to it automatically (see the top-level README). To run the frontend alone with sample signs only:

```bash
cd frontend
python3 -m http.server 8080
```

Open http://localhost:8080 on a laptop. For a phone, serve over HTTPS (camera and microphone need a secure origin), then use Chrome's "Install app".

## What works without a backend

- Five sample signs (bus board, pharmacy, pedestrian signal, metro platform, blurry board) with scripted answers in English, Hindi and Telugu.
- Real frame-quality check on every photo: blur, brightness and steadiness, reported in words.
- Live camera with spoken alignment cues and auto-capture once the frame is steady.
- Voice input (browser speech recognition) with read-back confirmation when confidence is low.
- Spoken answers (browser text-to-speech), captions, vibration and flash alerts.
- Three profiles (blind or low vision, deaf or hard of hearing, older adult), Repeat, Explain simpler, Tell me more, Mute, speed and text size.
- Profile suggestions from interaction signals, always confirmed by the user.
- Plain assistant vs SignSaathi comparison, pipeline trace, simulated network drop.

Pipeline timings and sample distances or bus times are examples.

## Backend contract

Set the backend URL in Settings. Photos from the camera or an upload are sent to:

`POST {backend}/api/ask` (multipart form)

| field | value |
|---|---|
| image | JPEG of the sign |
| query | the question as text, in the user's language |
| lang | `en`, `hi` or `te` |
| profile | `visual`, `hearing` or `ageing` |

Response (JSON):

```json
{
  "read_text": "text found on the sign",
  "answer": "one-sentence answer in the user's language",
  "simple": "simpler version",
  "more": "extra detail",
  "confidence": "high | medium | low",
  "needs_retake": false,
  "retake_hint": "Move the phone left and hold still."
}
```

If the request fails, the app says so and keeps the sign text it already has. Enable CORS on the backend for the app's origin.

To wire in Bhashini, call ASR, NMT, OCR and TTS from the backend and return text. `speak()` plays Bhashini audio from the backend (`audio_b64` in the `/api/ask` response, or `POST /api/tts` for other text) and falls back to the browser voice.

## Files

- `index.html` app, styles and logic
- `manifest.webmanifest` install metadata
- `sw.js` offline app shell
- `icons/icon.svg` app icon

## Known limits

- Telugu and Hindi voices depend on the device. If none is installed, the app shows captions and says so.
- Browser speech recognition needs Chrome on Android or desktop and a network connection.
- Photos other than the samples need the backend to be read.
