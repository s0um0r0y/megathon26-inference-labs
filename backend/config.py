"""Runtime settings, read from environment variables or backend/.env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Language services provider: "canvas" (IIIT Bhashini sandbox) or "ulca".
    language_provider: Literal["canvas", "ulca"] = "canvas"

    # IIIT Bhashini sandbox (canvas.iiit.ac.in). Auth: an access token, or email +
    # password so the backend can log in (and log in again when the token expires).
    canvas_base_url: str = "https://canvas.iiit.ac.in/sandboxbeprod"
    canvas_access_token: str = ""
    canvas_email: str = ""
    canvas_password: str = ""
    # Model IDs: the last part of each service URL on the sandbox. Empty = unavailable.
    canvas_asr_en_model: str = ""
    canvas_asr_hi_model: str = ""
    canvas_asr_te_model: str = ""
    canvas_nmt_hi_en_model: str = ""
    canvas_nmt_en_hi_model: str = ""
    canvas_nmt_te_en_model: str = ""
    canvas_nmt_en_te_model: str = ""
    canvas_tts_en_model: str = ""
    canvas_tts_hi_model: str = ""
    canvas_tts_te_model: str = ""
    canvas_ocr_model: str = ""

    # Public Bhashini ULCA (LANGUAGE_PROVIDER=ulca) - https://bhashini.gitbook.io/bhashini-apis
    bhashini_user_id: str = ""
    bhashini_api_key: str = ""
    bhashini_pipeline_id: str = "64392f96daac500b55c543cd"  # MeitY pipeline (ASR/NMT/TTS)
    bhashini_config_url: str = (
        "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
    )

    # Vision reasoning (and OCR fallback): "anthropic" or "openai_compat".
    vision_provider: Literal["anthropic", "openai_compat"] = "anthropic"

    # OpenAI-compatible server for open models, e.g.
    #   Ollama (local):  http://localhost:11434/v1   model qwen2.5vl:7b / llama3.2-vision:11b
    #   Groq (hosted):   https://api.groq.com/openai/v1   model meta-llama/llama-4-scout-17b-16e-instruct
    openai_base_url: str = ""
    openai_api_key: str = ""  # empty for local servers
    openai_model: str = ""
    # json_object is the safe default: grammar-constrained json_schema makes small
    # local models (e.g. qwen2.5vl:7b on Ollama) loop until the server aborts.
    openai_json_mode: Literal["json_object", "json_schema"] = "json_object"
    # Downscale photos before sending to open models (fewer image tokens = much
    # faster on a laptop GPU). 0 disables.
    vision_max_side: int = 768
    # Separate OCR pass on the vision model when no OCR service is set. Default:
    # on for Claude, off for open models (it doubles latency on a local GPU).
    ocr_vision_fallback: bool | None = None

    # Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    # Street use is latency-sensitive; raise to "medium"/"high" if answers get sloppy.
    anthropic_effort: str = "low"

    # Optional dedicated OCR provider. Empty -> OCR falls back to the vision model.
    google_vision_api_key: str = ""

    # OpenStreetMap
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org/reverse"
    osm_user_agent: str = "SignSaathi/0.1 (Megathon 2026 accessibility prototype)"

    # Deadlines (seconds)
    request_deadline_s: float = 25.0
    asr_timeout_s: float = 8.0
    ocr_timeout_s: float = 8.0
    nmt_timeout_s: float = 5.0
    vision_timeout_s: float = 18.0
    maps_timeout_s: float = 6.0
    tts_timeout_s: float = 6.0

    session_ttl_s: int = 60 * 60
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
