# Setup Checklist

Use this checklist before a local operator runs EPUB Chapters Studio.

- Install Python 3.11 or newer.
- Install Node.js 22.13.1 or newer.
- Install `ffmpeg` and confirm `ffmpeg -version` works.
- Install `ffprobe` and confirm `ffprobe -version` works.
- Run `./scripts/launch-local.sh` from the project root.
- Open `http://127.0.0.1:4321`.
- Optional: copy `.env.example` to `.env` and set local cache paths for `HF_HOME` and `TORCH_HOME`.
- Optional: set `EPUB_CHAPTERS_API_DATA_DIR` to a local workspace directory with enough disk space for rendered WAV and M4B files.
- Keep `.env`, model caches, generated renders, and downloaded model data out of version control.
