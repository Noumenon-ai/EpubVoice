# EPUB Chapters Studio

EPUB Chapters Studio is a localhost audiobook mastering tool. It parses an EPUB into editable chapters, previews Chatterbox TTS settings, renders one WAV per included chapter, and muxes a chapterized M4B with `ffmpeg`. The UI is a built Vite/React studio served by the local FastAPI process.

The app is designed for single-user local desktop use. It has no accounts, payments, cloud database, analytics, or stored personal data.

## Install

Requirements:

- Python 3.11 or newer
- Node.js 22.13.1 or newer
- `ffmpeg` and `ffprobe` on `PATH`
- A GPU-compatible PyTorch/Chatterbox setup for practical local synthesis

Install everything manually:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[synth,test]"
npm install
npm run build
```

Or use the one-command local launch, which creates `.venv`, installs Python dependencies, installs npm dependencies, builds the frontend, and starts the combined app:

```bash
./scripts/launch-local.sh
```

Open `http://127.0.0.1:4321`.

## Configuration

Copy the example only when you want to override defaults:

```bash
cp .env.example .env
```

Useful settings:

- `EPUB_CHAPTERS_HOST`: loopback host for the local server. Defaults to `127.0.0.1`.
- `EPUB_CHAPTERS_PORT`: local server port. Defaults to `4321`; ports `3000` and `3001` are refused.
- `EPUB_CHAPTERS_API_DATA_DIR`: local uploads, previews, and renders directory. Defaults to `.local_api_data`.
- `EPUB_CHAPTERS_FRONTEND_DIST`: built frontend directory. Defaults to `dist`.
- `HF_HOME` and `TORCH_HOME`: optional local model/cache directories.
- `CHATTERBOX_MODEL_PATH`: optional model path for environments that support loading Chatterbox from a local path.

Do not commit `.env`, model caches, generated renders, or downloaded model files.

## Run

Production-style local run:

```bash
./scripts/launch-local.sh
```

API-only development run:

```bash
. .venv/bin/activate
python -m uvicorn epub_chapters.api:app --host 127.0.0.1 --port 4321
```

Frontend-only development run:

```bash
npm run build
npm test
```

The Vite dev server configuration uses `127.0.0.1:4322` when a frontend dev server is needed. The production local launcher serves the built frontend from FastAPI on `4321`.

## Test

Requested Phase 5 verification:

```bash
pytest tests/test_e2e.py -q
```

Full local validation:

```bash
pytest -q
npm run build
npm test
```

The e2e smoke test builds a tiny EPUB fixture, mocks only the TTS waveform generation, uses real `ffmpeg` to create an M4B, and uses `ffprobe` to assert the output container has two chapter markers.

## Key Entry Points

- `epub_chapters/parser.py`: EPUB spine parsing and chapter extraction.
- `epub_chapters/editor.py`: editable chapter model operations.
- `epub_chapters/synth.py`: Chatterbox adapter, WAV writing, `ffmpeg` M4B muxing, chapter metadata.
- `epub_chapters/api.py`: FastAPI routes, validation, structured logs, render jobs, `/health`, built frontend serving.
- `epub_chapters/launch.py`: local combined-app launcher.
- `src/App.tsx`: recording-studio React workspace.
- `src/components/ChapterTimeline.tsx`: chapter waveform timeline and split controls.
- `tests/test_e2e.py`: Phase 5 EPUB-to-M4B smoke test.

## Troubleshooting

`ffmpeg executable not found`

Install `ffmpeg` so both `ffmpeg` and `ffprobe` are available on `PATH`. The e2e test and M4B export require both binaries.

GPU or Chatterbox load failures

Confirm your Python environment has the correct PyTorch build for your GPU driver or CPU fallback. Keep `HF_HOME` and `TORCH_HOME` pointed at writable local cache directories if the model downloader cannot write to its default cache.

Port refused at startup

Use `EPUB_CHAPTERS_PORT=4323 ./scripts/launch-local.sh`. The launcher intentionally refuses `3000` and `3001`.

Frontend build not found

Run `npm run build`, or use `./scripts/launch-local.sh`, which builds the frontend before starting the server.
