# Deployment

The EPUB Audiobook Studio ships as a single container image: a multi-stage
`Dockerfile` builds the Vite/React UI, then a Python runtime serves both the
FastAPI API and the compiled UI from one uvicorn process.

## Security model (read first)

This service has **no built-in authentication**. It is a single-user studio
tool. Inside the container uvicorn binds `0.0.0.0` so the port is reachable,
but you must not expose it directly to the public internet.

- Run it on a private network, a VPN, or `localhost` only.
- If it must be reachable remotely, put it behind an authenticated reverse
  proxy (for example nginx/Caddy with basic auth or an identity-aware proxy).
- Uploaded EPUBs and rendered audio live in the data volume (`/data`). Treat
  that volume as private user content.

See `SECURITY_PRIVACY_NOTES.md` for the full data-handling notes.

## Build

```bash
# Base image (API + UI). Voice preview / render endpoints are disabled until
# the synthesis extra is installed.
docker build -t epub-studio .

# Full image including the Chatterbox TTS synthesis stack (large; pulls torch).
docker build --build-arg INSTALL_SYNTH=true -t epub-studio:synth .
```

## Run

```bash
docker run --rm \
  -p 127.0.0.1:4321:4321 \
  -v "$(pwd)/.local_api_data:/data" \
  --name epub-studio \
  epub-studio
```

Then open <http://127.0.0.1:4321/>. The `/health` endpoint returns
`{"status":"ok"}` and is also wired into the image `HEALTHCHECK`.

Binding to `127.0.0.1` on the host (as above) keeps the studio reachable only
from the local machine.

## Environment variables

These are read by `create_app()` at startup (see `.env.example` for the full
list). The container sets sensible defaults; override with `-e` as needed.

| Variable | Default in image | Purpose |
| --- | --- | --- |
| `EPUB_CHAPTERS_PORT` | `4321` | Port uvicorn listens on. |
| `EPUB_CHAPTERS_FRONTEND_DIST` | `/app/dist` | Compiled UI served by the API. |
| `EPUB_CHAPTERS_API_DATA_DIR` | `/data` | Where uploads and renders are stored (mount a volume). |
| `EPUB_CHAPTERS_API_CORS_ORIGINS` | localhost UI origins | Comma-separated CORS allow-list. Never `*`. |
| `CHATTERBOX_MODEL_PATH`, `HF_HOME`, `TORCH_HOME` | unset | Optional model/cache locations (synth build only). |

`EPUB_CHAPTERS_HOST` from `.env.example` applies only to the loopback-only
desktop launcher (`epub_chapters.launch`); the container deliberately binds
`0.0.0.0` via uvicorn instead.

## Platform notes

The image follows the standard 12-factor container contract (config via env,
listens on `$EPUB_CHAPTERS_PORT`, `/health` liveness), so it deploys to any
container host (Fly.io, Render, Cloud Run, ECS, a plain VM with Docker). On
platforms that inject their own `$PORT`, run with
`-e EPUB_CHAPTERS_PORT=$PORT`. Always pair a remote deployment with the
authentication layer described above.

CI (`.github/workflows/ci.yml`) runs the frontend tests + build, the backend
test suite, and a no-push `docker build` to keep this image green on every PR.
