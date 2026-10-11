# SignSaathi

## Prerequisites

- Linux or macOS
- Python 3.11 or newer, managed with [uv](https://docs.astral.sh/uv/)
- Node.js 20 or newer and npm
- An Android phone with Chrome, on the same network as the computer (optional, for testing on a phone)
- [Ollama](https://ollama.com) if you run the vision model locally (optional)

## 1. Configure

```bash
cp backend/.env.example backend/.env
```

Fill in `backend/.env`:

- **Language services:** `CANVAS_ACCESS_TOKEN`, or `CANVAS_EMAIL` and `CANVAS_PASSWORD`, plus the `CANVAS_*_MODEL` IDs from the IIIT Bhashini sandbox.
- **Vision model:** pick one of the following.
  - Local Ollama: `VISION_PROVIDER=openai_compat`, `OPENAI_BASE_URL=http://localhost:11434/v1`, `OPENAI_MODEL=qwen2.5vl:7b`
  - Hosted (for example Groq): `VISION_PROVIDER=openai_compat` with that service's `OPENAI_BASE_URL`, `OPENAI_MODEL` and `OPENAI_API_KEY`
  - Claude: `VISION_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`

If you use Ollama, start it and download the model:

```bash
ollama serve &
ollama pull qwen2.5vl:7b
```

## 2. Backend

```bash
cd backend
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

To check it, run `curl http://localhost:8000/api/health`. It lists which services are configured.

To run the tests:

```bash
cd backend
uv run pytest -q
```

If pytest fails at startup with errors from other installed packages (for example a ROS install), prefix the commands with `env -u PYTHONPATH`.

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `https://localhost:5173` on the computer. On the phone, open `https://<computer-LAN-IP>:5173` and accept the self-signed certificate warning once. The camera and microphone only work over HTTPS. The dev server forwards `/api` and `/ws` to the backend on port 8000.

To run the checks and tests:

```bash
cd frontend
npm run typecheck
npm test
```

## 4. Production build

```bash
cd frontend
npm run build      # output in frontend/dist
npm run preview    # serves the build on https://localhost:4173
```

To serve `frontend/dist` behind any HTTPS web server, forward `/api` to the backend and `/ws` to the backend as a WebSocket.

## License

MIT. See [LICENSE](LICENSE).
