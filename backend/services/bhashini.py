"""Language services (ASR, NMT, TTS, and sign OCR) behind one interface.

Two providers, picked by `make_language_client`:

- CanvasClient: the IIIT Bhashini sandbox (canvas.iiit.ac.in/sandboxbeprod), the
  hackathon's provider. One access token, one model ID per service/language. Request
  shapes come from its published OpenAPI schema (/openapi.json); NMT and TTS
  response shapes were confirmed against the live service.
- UlcaClient: the public Bhashini ULCA flow (user ID + ULCA API key -> per-task
  serviceId and inference endpoint -> Dhruva-format compute calls).

Both expose: configured, services(), asr(), translate(), translate_many(), tts(),
and (Canvas only) ocr().
"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from config import Settings
from schemas.request import Language

log = logging.getLogger(__name__)

PAIRS = (("hi", "en"), ("en", "hi"), ("te", "en"), ("en", "te"))


class BhashiniError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsrResult:
    text: str
    # Neither provider returns a score; this is a heuristic from transcript shape (see confidence.py).
    confidence: float


def _asr_result(text: str) -> AsrResult:
    from safety.confidence import asr_confidence  # avoid import cycle at module load

    return AsrResult(text=text, confidence=asr_confidence(text))


# ---- IIIT Canvas sandbox ----------------------------------------------------------------

_TEXT_KEYS = ("output_text", "transcript", "transcription", "text", "source", "output", "result", "prediction")


def _find_text(data: Any) -> str | None:
    """First plausible text field in a response payload.

    ASR and OCR response shapes are not in the sandbox's schema, so this looks for
    common keys (then any string) instead of one fixed path. Lists of lines are joined.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = [t for t in (_find_text(x) for x in data) if t]
        return "\n".join(parts) if parts else None
    if isinstance(data, dict):
        for key in _TEXT_KEYS:
            if key in data:
                found = _find_text(data[key])
                if found is not None:
                    return found
        for value in data.values():
            found = _find_text(value)
            if found is not None:
                return found
    return None


class CanvasClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._s = settings
        self._base = settings.canvas_base_url.rstrip("/")
        self._token = settings.canvas_access_token
        self._login_lock = asyncio.Lock()

    # -- configuration --

    def _model(self, name: str) -> str:
        return getattr(self._s, f"canvas_{name}_model", "")

    @property
    def has_credentials(self) -> bool:
        return bool(self._token or (self._s.canvas_email and self._s.canvas_password))

    @property
    def configured(self) -> bool:
        return self.has_credentials and any(v for k, v in self.services().items())

    def services(self) -> dict[str, bool]:
        out = {}
        for lang in Language:
            out[f"asr_{lang}"] = bool(self._model(f"asr_{lang}"))
            out[f"tts_{lang}"] = bool(self._model(f"tts_{lang}"))
        for a, b in PAIRS:
            out[f"nmt_{a}_{b}"] = bool(self._model(f"nmt_{a}_{b}"))
        out["ocr"] = bool(self._s.canvas_ocr_model)
        return out

    def _require(self, name: str) -> str:
        model = self._model(name)
        if not model:
            raise BhashiniError(f"no Canvas model configured for {name}")
        if not self.has_credentials:
            raise BhashiniError("no Canvas access token or login configured")
        return model

    # -- auth --

    async def _login(self) -> None:
        """Exchange email + password for an access token (POST /login)."""
        if not (self._s.canvas_email and self._s.canvas_password):
            raise BhashiniError("Canvas token rejected and no email/password to log in again")
        async with self._login_lock:
            resp = await self._http.post(
                f"{self._base}/login",
                json={"email": self._s.canvas_email, "password": self._s.canvas_password},
            )
            body = resp.json()
            token = _find_token(body)
            if not token:
                raise BhashiniError(f"Canvas login failed: {str(body.get('message', body))[:200]}")
            self._token = token
            log.info("Canvas login succeeded")

    async def _post(self, path: str, **kw) -> dict:
        """POST with the access token; unwraps {status, message, data}. Logs in again
        once if the token is missing or expired."""
        if not self._token:
            await self._login()
        for attempt in (1, 2):
            resp = await self._http.post(
                f"{self._base}/{path}", headers={"access-token": self._token}, **kw
            )
            try:
                body = resp.json()
            except ValueError as e:
                raise BhashiniError(f"Canvas {path}: HTTP {resp.status_code}, non-JSON body") from e
            status = str(body.get("status", "")).lower()
            code = body.get("code", resp.status_code)
            if status == "success" or (resp.status_code == 200 and status == "" and "data" in body):
                return body.get("data") or {}
            message = str(body.get("message") or body.get("error") or body)
            auth_problem = code in (401, 403) or "token" in message.lower()
            if attempt == 1 and auth_problem and self._s.canvas_email and self._s.canvas_password:
                await self._login()
                continue
            raise BhashiniError(f"Canvas {path.split('/')[0]}: {message[:200]}")
        raise BhashiniError("unreachable")

    # -- services --

    async def asr(self, wav_b64: str, lang: Language) -> AsrResult:
        model = self._require(f"asr_{lang}")
        data = await self._post(
            f"infer_asr/{model}",
            files={"audio_file": ("question.wav", base64.b64decode(wav_b64), "audio/wav")},
        )
        text = _find_text(data)
        if text is None:
            raise BhashiniError(f"no transcript in ASR response: {str(data)[:200]}")
        return _asr_result(text.strip())

    async def translate(self, text: str, src: Language, tgt: Language) -> str:
        if not text.strip() or src == tgt:
            return text
        return (await self.translate_many([text], src, tgt))[0]

    async def translate_many(self, texts: list[str], src: Language, tgt: Language) -> list[str]:
        """One batched call; the sandbox accepts and returns a list of strings."""
        if src == tgt:
            return list(texts)
        model = self._require(f"nmt_{src}_{tgt}")
        idx = [i for i, t in enumerate(texts) if t.strip()]
        if not idx:
            return list(texts)
        data = await self._post(
            f"check_model_status_and_infer/{model}", json={"input_text": [texts[i] for i in idx]}
        )
        out = data.get("output_text")
        if isinstance(out, str):
            out = [out]
        if not isinstance(out, list) or len(out) != len(idx):
            raise BhashiniError(f"NMT returned {out!r} for {len(idx)} inputs")
        result = list(texts)
        for i, t in zip(idx, out):
            # "........" is what the sandbox returns for input in the wrong language.
            if not isinstance(t, str) or not t.strip(" ."):
                raise BhashiniError(f"NMT {src}->{tgt} produced no translation (wrong model for this pair?)")
            result[i] = t
        return result

    async def tts(self, text: str, lang: Language, gender: str = "female") -> tuple[str, str]:
        model = self._require(f"tts_{lang}")
        data = await self._post(f"generate_tts/{model}", json={"text": text, "gender": gender})
        url = data.get("s3_url") or data.get("audio_url") or data.get("url")
        if not url:
            raise BhashiniError(f"no audio URL in TTS response: {str(data)[:200]}")
        audio = await self._http.get(url)
        audio.raise_for_status()
        mime = audio.headers.get("content-type", "audio/wav").split(";")[0]
        if not mime.startswith("audio/"):
            mime = "audio/wav"
        return base64.b64encode(audio.content).decode(), mime

    async def ocr(self, image: bytes) -> str:
        model = self._s.canvas_ocr_model
        if not model:
            raise BhashiniError("no Canvas OCR model configured")
        data = await self._post(
            f"check_ocr_status_and_infer/{model}", files={"file": ("sign.jpg", image, "image/jpeg")}
        )
        text = _find_text(data)
        if text is None:
            raise BhashiniError(f"no text in OCR response: {str(data)[:200]}")
        return text.strip()


def _find_token(body: Any) -> str | None:
    if isinstance(body, dict):
        for key in ("access_token", "accessToken", "access-token", "token"):
            if isinstance(body.get(key), str) and body[key]:
                return body[key]
        for value in body.values():
            found = _find_token(value)
            if found:
                return found
    return None


# ---- Public Bhashini ULCA ---------------------------------------------------------------


@dataclass(frozen=True)
class _TaskConfig:
    service_id: str
    callback_url: str
    auth_header: tuple[str, str]


class UlcaClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._s = settings
        self._configs: dict[tuple, _TaskConfig] = {}
        self._config_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._s.bhashini_user_id and self._s.bhashini_api_key)

    def services(self) -> dict[str, bool]:
        ok = self.configured
        out = {f"{t}_{lang}": ok for lang in Language for t in ("asr", "tts")}
        out.update({f"nmt_{a}_{b}": ok for a, b in PAIRS})
        return out

    async def _config(self, task: str, src: Language, tgt: Language | None = None) -> _TaskConfig:
        key = (task, src, tgt)
        if key in self._configs:
            return self._configs[key]
        async with self._config_lock:
            if key in self._configs:
                return self._configs[key]
            language = {"sourceLanguage": src.value}
            if tgt:
                language["targetLanguage"] = tgt.value
            resp = await self._http.post(
                self._s.bhashini_config_url,
                headers={
                    "userID": self._s.bhashini_user_id,
                    "ulcaApiKey": self._s.bhashini_api_key,
                },
                json={
                    "pipelineTasks": [{"taskType": task, "config": {"language": language}}],
                    "pipelineRequestConfig": {"pipelineId": self._s.bhashini_pipeline_id},
                },
            )
            resp.raise_for_status()
            body = resp.json()
            try:
                service_id = body["pipelineResponseConfig"][0]["config"][0]["serviceId"]
                endpoint = body["pipelineInferenceAPIEndPoint"]
                auth = endpoint["inferenceApiKey"]
                cfg = _TaskConfig(service_id, endpoint["callbackUrl"], (auth["name"], auth["value"]))
            except (KeyError, IndexError) as e:
                raise BhashiniError(f"no {task} service for {src}->{tgt}") from e
            self._configs[key] = cfg
            return cfg

    async def _compute(self, cfg: _TaskConfig, task: str, task_config: dict, input_data: dict) -> dict:
        resp = await self._http.post(
            cfg.callback_url,
            headers={cfg.auth_header[0]: cfg.auth_header[1]},
            json={
                "pipelineTasks": [{"taskType": task, "config": task_config}],
                "inputData": input_data,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def asr(self, wav_b64: str, lang: Language) -> AsrResult:
        """Speech to text. Expects 16 kHz mono WAV."""
        cfg = await self._config("asr", lang)
        body = await self._compute(
            cfg,
            "asr",
            {
                "language": {"sourceLanguage": lang.value},
                "serviceId": cfg.service_id,
                "audioFormat": "wav",
                "samplingRate": 16000,
            },
            {"audio": [{"audioContent": wav_b64}]},
        )
        try:
            text = body["pipelineResponse"][0]["output"][0]["source"].strip()
        except (KeyError, IndexError) as e:
            raise BhashiniError("malformed ASR response") from e
        return _asr_result(text)

    async def translate(self, text: str, src: Language, tgt: Language) -> str:
        if not text.strip() or src == tgt:
            return text
        cfg = await self._config("translation", src, tgt)
        body = await self._compute(
            cfg,
            "translation",
            {
                "language": {"sourceLanguage": src.value, "targetLanguage": tgt.value},
                "serviceId": cfg.service_id,
            },
            {"input": [{"source": text}]},
        )
        try:
            return body["pipelineResponse"][0]["output"][0]["target"]
        except (KeyError, IndexError) as e:
            raise BhashiniError("malformed NMT response") from e

    async def translate_many(self, texts: list[str], src: Language, tgt: Language) -> list[str]:
        """Translate several strings in parallel, preserving order."""
        if src == tgt:
            return list(texts)
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self.translate(t, src, tgt)) for t in texts]
        return [t.result() for t in tasks]

    async def tts(self, text: str, lang: Language, gender: str = "female") -> tuple[str, str]:
        """Returns (base64 audio, mime type)."""
        cfg = await self._config("tts", lang)
        body = await self._compute(
            cfg,
            "tts",
            {"language": {"sourceLanguage": lang.value}, "serviceId": cfg.service_id, "gender": gender},
            {"input": [{"source": text}]},
        )
        try:
            audio = body["pipelineResponse"][0]["audio"][0]["audioContent"]
        except (KeyError, IndexError) as e:
            raise BhashiniError("malformed TTS response") from e
        return audio, "audio/wav"


LanguageClient = CanvasClient | UlcaClient


def make_language_client(http: httpx.AsyncClient, settings: Settings) -> LanguageClient:
    if settings.language_provider == "ulca":
        return UlcaClient(http, settings)
    return CanvasClient(http, settings)
