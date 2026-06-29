#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required.")
PY

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON=".venv/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip

PY_EXTRAS="${EPUB_CHAPTERS_PIP_EXTRAS:-synth}"
"$VENV_PYTHON" -m pip install -e ".[${PY_EXTRAS}]"

npm install
npm run build

export EPUB_CHAPTERS_FRONTEND_DIST="${EPUB_CHAPTERS_FRONTEND_DIST:-$ROOT_DIR/dist}"
export EPUB_CHAPTERS_API_DATA_DIR="${EPUB_CHAPTERS_API_DATA_DIR:-$ROOT_DIR/.local_api_data}"
export EPUB_CHAPTERS_PORT="${EPUB_CHAPTERS_PORT:-4321}"
export EPUB_CHAPTERS_HOST="${EPUB_CHAPTERS_HOST:-127.0.0.1}"

exec "$VENV_PYTHON" -m epub_chapters.launch
