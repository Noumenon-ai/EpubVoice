from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .api import create_app


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")

    host = os.environ.get("EPUB_CHAPTERS_HOST", "127.0.0.1")
    port = _env_port("EPUB_CHAPTERS_PORT", 4321)
    dist = Path(os.environ.get("EPUB_CHAPTERS_FRONTEND_DIST", root / "dist"))
    data_dir = Path(os.environ.get("EPUB_CHAPTERS_API_DATA_DIR", root / ".local_api_data"))

    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("EPUB_CHAPTERS_HOST must be 127.0.0.1 or localhost for the local desktop launcher")

    app = create_app(storage_root=data_dir, frontend_dist=dist)
    uvicorn.run(app, host=host, port=port, log_config=None)


def _env_port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer") from exc
    if not 1024 <= port <= 65535 or port in {3000, 3001}:
        raise SystemExit(f"{name} must be between 1024 and 65535 and cannot be 3000 or 3001")
    return port


if __name__ == "__main__":
    main()
