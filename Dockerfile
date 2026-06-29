# syntax=docker/dockerfile:1.7

# Multi-stage build for the EPUB Audiobook Studio.
#
#   Stage 1 (frontend) compiles the Vite/React UI into static assets.
#   Stage 2 (runtime)  installs the FastAPI backend and serves the API plus
#                      the compiled UI from a single Python process.
#
# SECURITY: this service has NO built-in authentication. It is a single-user
# studio tool. Inside the container uvicorn binds 0.0.0.0 (required for the
# port to be reachable), so you MUST NOT publish this container directly to the
# public internet. Run it on a private network or behind an authenticated
# reverse proxy (see docs/DEPLOYMENT.md).

# ---------------------------------------------------------------------------
# Stage 1: build the frontend bundle
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /build

# Install dependencies first so this layer is cached across source changes.
COPY package.json package-lock.json ./
RUN npm ci

# Copy only what the Vite build needs, then produce the static bundle.
COPY tsconfig.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime serving API + compiled UI
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Set to "true" to bundle the Chatterbox TTS synthesis stack (large, pulls
# torch). Left off by default so the base image stays lean; voice preview and
# render endpoints require this extra. Build with:
#   docker build --build-arg INSTALL_SYNTH=true -t epub-studio .
ARG INSTALL_SYNTH=false

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EPUB_CHAPTERS_FRONTEND_DIST=/app/dist \
    EPUB_CHAPTERS_API_DATA_DIR=/data \
    EPUB_CHAPTERS_PORT=4321

WORKDIR /app

# Install the backend package and its dependencies (uvicorn, fastapi, etc.).
COPY pyproject.toml ./
COPY epub_chapters ./epub_chapters
RUN if [ "$INSTALL_SYNTH" = "true" ]; then \
        pip install ".[synth]"; \
    else \
        pip install .; \
    fi

# Bring in the compiled frontend from stage 1.
COPY --from=frontend /build/dist ./dist

# Run as an unprivileged user; give it ownership of the writable data dir.
RUN useradd --system --create-home --uid 10001 studio \
    && mkdir -p /data \
    && chown -R studio:studio /app /data
USER studio

EXPOSE 4321

# Liveness probe using the API's /health endpoint (no curl in slim image).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys; port=os.environ.get('EPUB_CHAPTERS_PORT','4321'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+port+'/health', timeout=4).status==200 else 1)"]

# create_app() reads EPUB_CHAPTERS_FRONTEND_DIST / EPUB_CHAPTERS_API_DATA_DIR
# from the environment. We bind 0.0.0.0 here (not via launch.py, which is the
# loopback-only desktop launcher) so the port is reachable from the host.
CMD ["sh", "-c", "exec uvicorn --factory epub_chapters.api:create_app --host 0.0.0.0 --port ${EPUB_CHAPTERS_PORT:-4321}"]
