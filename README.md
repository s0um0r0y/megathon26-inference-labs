# SignSaathi

## Prerequisites

- Linux or macOS
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 automatically, as set in `backend/uv.toml` and `backend/.python-version`)
- OpenSSL, to create a development certificate
- Optional: [Ollama](https://ollama.com) to run the vision model locally
- Optional: an Android phone with Chrome, on the same network as the computer

The frontend is static HTML, CSS and JavaScript. It has no build step, and the backend serves it.

## 1. Configure

```bash
cd backend
cp .env.example .env
```

Fill in `backend/.env`:

- **Language services (IIIT Bhashini sandbox):** `CANVAS_ACCESS_TOKEN`, or `CANVAS_EMAIL` and `CANVAS_PASSWORD`, plus the `CANVAS_*_MODEL` IDs.
- **Vision model:** pick one of the following.
  - Local Ollama: `VISION_PROVIDER=openai_compat`, `OPENAI_BASE_URL=http://localhost:11434/v1`, `OPENAI_MODEL=qwen2.5vl:7b`
  - Hosted: `VISION_PROVIDER=openai_compat` with that service's `OPENAI_BASE_URL`, `OPENAI_MODEL` and `OPENAI_API_KEY`
  - Claude: `VISION_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`

## 2. Start Ollama (local vision model only)

```bash
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=30m ollama serve &
ollama pull qwen2.5vl:7b
```

## 3. Install and run

```bash
cd backend
uv sync

# Development certificate (camera and microphone need HTTPS on a phone)
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=signsaathi-dev" \
  -keyout certs/dev.key -out certs/dev.crt

uv run uvicorn main:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile certs/dev.key --ssl-certfile certs/dev.crt
```

Open `https://localhost:8443` on the computer, or `https://<computer-LAN-IP>:8443` on the phone, and accept the certificate warning once. The app detects the backend automatically. To check which services are configured, open `https://localhost:8443/api/health`.

To run the app without HTTPS on the computer only:

```bash
uv run uvicorn main:app --port 8000      # then open http://localhost:8000
```

## 4. Tests

```bash
cd backend
uv run pytest -q
```

If pytest fails at startup with errors from other installed packages (for example a ROS install), run `env -u PYTHONPATH uv run pytest -q`.

## License

MIT. See [LICENSE](LICENSE).
