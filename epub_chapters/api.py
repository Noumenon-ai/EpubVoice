from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from .editor import ChapterBook
from .models import Chapter
from .normalizer import normalize_text
from .parser import EpubParseError, parse_epub
from .synth import ChapterAudio, ChatterboxSynthesizer, SynthOptions

MAX_EPUB_BYTES = 50 * 1024 * 1024
MAX_CHAPTER_TEXT_BYTES = 500_000
MAX_TITLE_CHARS = 200
MAX_PREVIEW_CHARS = 500

# The single-user UI is served from the Vite dev server on a different port than
# the API, so browser requests are cross-origin and need explicit CORS allowance.
# Origins are an allow-list (never "*"); deployments can override via the env var.
DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:4322",
    "http://localhost:4322",
)

logger = logging.getLogger("epub_chapters.api")


class ChapterResponse(BaseModel):
    id: str
    title: str
    text: str
    reading_order: int
    sentences: tuple[str, ...]
    excluded: bool


class BookResponse(BaseModel):
    book_id: str
    chapter_count: int
    chapters: tuple[ChapterResponse, ...]


class ChapterUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_CHARS)
    text: str | None = Field(default=None, min_length=1)
    excluded: bool | None = None

    @field_validator("title", "text")
    @classmethod
    def normalize_non_empty(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError(f"{info.field_name} cannot be empty")
        if info.field_name == "text" and len(normalized.encode("utf-8")) > MAX_CHAPTER_TEXT_BYTES:
            raise ValueError("text is too large")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ChapterUpdateRequest":
        if self.title is None and self.text is None and self.excluded is None:
            raise ValueError("at least one chapter field must be supplied")
        return self


class TtsOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exaggeration: float | None = Field(default=None, ge=0.0, le=2.0)
    cfg_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    pace_weight: float | None = Field(default=None, ge=0.0, le=2.0)
    temperature: float | None = Field(default=None, ge=0.0, le=5.0)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    reference_voice_path: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("reference_voice_path")
    @classmethod
    def validate_reference_voice_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError("reference_voice_path must be an existing file")
        return str(path)

    def to_synth_options(self) -> SynthOptions:
        return SynthOptions(
            exaggeration=self.exaggeration,
            cfg_weight=self.cfg_weight,
            pace_weight=self.pace_weight,
            temperature=self.temperature,
            seed=self.seed,
            reference_voice_path=self.reference_voice_path,
        )


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_line: str = Field(default="This is a short voice preview.", min_length=1, max_length=MAX_PREVIEW_CHARS)
    options: TtsOptionsRequest = Field(default_factory=TtsOptionsRequest)

    @field_validator("sample_line")
    @classmethod
    def normalize_sample_line(cls, value: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("sample_line cannot be empty")
        return normalized


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(min_length=1, max_length=80)
    output_name: str = Field(default="audiobook", min_length=1, max_length=120)
    options: TtsOptionsRequest = Field(default_factory=TtsOptionsRequest)

    @field_validator("output_name")
    @classmethod
    def normalize_output_name(cls, value: str) -> str:
        normalized = _safe_name(value)
        if not normalized:
            raise ValueError("output_name must contain at least one filename-safe character")
        return normalized


class ParameterResponse(BaseModel):
    name: str
    type: Literal["number", "integer", "string"]
    default: float | int | str | None
    minimum: float | int | None = None
    maximum: float | int | None = None
    nullable: bool = False


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    book_id: str
    total_chapters: int
    completed_chapters: int
    current_chapter_id: str | None
    output_path: str | None
    error: str | None


class ApiState:
    def __init__(
        self,
        *,
        storage_root: Path,
        engine_factory: Callable[[], object],
        executor: Executor,
    ) -> None:
        self.storage_root = storage_root
        self.upload_root = storage_root / "uploads"
        self.render_root = storage_root / "renders"
        self.preview_root = storage_root / "previews"
        self.engine_factory = engine_factory
        self.executor = executor
        self.lock = threading.RLock()
        self._engine: object | None = None
        self._engine_lock = threading.Lock()
        self.books: dict[str, ChapterBook] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.futures: dict[str, Future[Any]] = {}
        self.cancel_events: dict[str, threading.Event] = {}

        for directory in (self.upload_root, self.render_root, self.preview_root):
            directory.mkdir(parents=True, exist_ok=True)

    def get_engine(self) -> object:
        """Resolve the synthesis engine once and reuse it.

        The default engine is a ``ChatterboxSynthesizer`` whose construction
        loads a large pretrained TTS model. Building it per request would make
        every preview/render reload the model, so the engine is a thread-safe
        lazily-initialized singleton shared across requests and worker threads.
        """
        engine = self._engine
        if engine is not None:
            return engine
        with self._engine_lock:
            if self._engine is None:
                self._engine = self.engine_factory()
            return self._engine


def create_app(
    *,
    engine: object | None = None,
    engine_factory: Callable[[], object] | None = None,
    storage_root: str | Path | None = None,
    executor: Executor | None = None,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    configure_structured_logging()
    resolved_storage = Path(storage_root or os.environ.get("EPUB_CHAPTERS_API_DATA_DIR", ".local_api_data"))
    factory = engine_factory or (lambda: engine if engine is not None else ChatterboxSynthesizer())
    state = ApiState(
        storage_root=resolved_storage,
        engine_factory=factory,
        executor=executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="render-job"),
    )
    app = FastAPI(title="EPUB Chapters API", version="0.1.0")
    app.state.api_state = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_resolved_cors_origins()),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/epubs", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
    def upload_epub(file: Annotated[UploadFile, File(...)]) -> BookResponse:
        _validate_upload_metadata(file)
        book_id = uuid.uuid4().hex
        destination = state.upload_root / f"{book_id}.epub"
        try:
            _copy_upload(file.file, destination)
            chapters = parse_epub(destination)
            book = ChapterBook(chapters)
        except (EpubParseError, ValueError) as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to store EPUB") from exc

        with state.lock:
            state.books[book_id] = book
        _log("epub_uploaded", book_id=book_id, chapter_count=len(book.chapters))
        return _book_response(book_id, book)

    @app.get("/books/{book_id}/chapters", response_model=tuple[ChapterResponse, ...])
    def list_chapters(book_id: str) -> tuple[ChapterResponse, ...]:
        book = _book_or_404(state, book_id)
        return tuple(_chapter_response(chapter) for chapter in book.chapters)

    @app.get("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterResponse)
    def get_chapter(book_id: str, chapter_id: str) -> ChapterResponse:
        chapter = _chapter_or_404(_book_or_404(state, book_id), chapter_id)
        return _chapter_response(chapter)

    @app.patch("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterResponse)
    def update_chapter(book_id: str, chapter_id: str, payload: ChapterUpdateRequest) -> ChapterResponse:
        book = _book_or_404(state, book_id)
        try:
            if payload.title is not None:
                chapter = book.rename(chapter_id, payload.title)
            else:
                chapter = _chapter_or_404(book, chapter_id)
            if payload.text is not None:
                chapter = book.edit_text(chapter.id, payload.text)
            if payload.excluded is not None:
                chapter = book.exclude(chapter.id, payload.excluded)
        except (KeyError, ValueError) as exc:
            raise _chapter_exception(exc) from exc
        _log("chapter_updated", book_id=book_id, chapter_id=chapter.id)
        return _chapter_response(chapter)

    @app.get("/tts/parameters", response_model=tuple[ParameterResponse, ...])
    def list_tts_parameters() -> tuple[ParameterResponse, ...]:
        return (
            ParameterResponse(name="exaggeration", type="number", default=0.5, minimum=0.0, maximum=2.0),
            ParameterResponse(name="cfg_weight", type="number", default=0.5, minimum=0.0, maximum=2.0),
            ParameterResponse(name="pace_weight", type="number", default=1.0, minimum=0.0, maximum=2.0),
            ParameterResponse(name="temperature", type="number", default=0.8, minimum=0.0, maximum=5.0),
            ParameterResponse(name="seed", type="integer", default=None, minimum=0, maximum=2_147_483_647, nullable=True),
            ParameterResponse(name="reference_voice_path", type="string", default=None, nullable=True),
        )

    @app.post("/tts/preview")
    def voice_preview(payload: PreviewRequest) -> Response:
        preview_path = state.preview_root / f"{uuid.uuid4().hex}.wav"
        try:
            audio = state.get_engine().synthesize_preview(
                preview_path,
                sample_line=payload.sample_line,
                options=payload.options.to_synth_options(),
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            _log("voice_preview_failed", error=exc.__class__.__name__)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="voice preview failed") from exc
        _log("voice_preview_created", audio_bytes=len(audio))
        return Response(content=audio, media_type="audio/wav")

    @app.post("/render-jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def start_render_job(payload: RenderRequest) -> JobResponse:
        book = _book_or_404(state, payload.book_id)
        included = book.included()
        if not included:
            raise HTTPException(status_code=422, detail="at least one included chapter is required")

        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "status": "queued",
            "book_id": payload.book_id,
            "total_chapters": len(included),
            "completed_chapters": 0,
            "current_chapter_id": None,
            "output_path": None,
            "error": None,
            "output_name": payload.output_name,
        }
        cancel_event = threading.Event()
        with state.lock:
            state.jobs[job_id] = job
            state.cancel_events[job_id] = cancel_event
            future = state.executor.submit(_run_render_job, state, job_id, tuple(included), payload)
            state.futures[job_id] = future
        _log("render_job_started", job_id=job_id, book_id=payload.book_id, total_chapters=len(included))
        return _job_response(job)

    @app.get("/render-jobs/{job_id}", response_model=JobResponse)
    def get_render_job(job_id: str) -> JobResponse:
        return _job_response(_job_or_404(state, job_id))

    @app.post("/render-jobs/{job_id}/cancel", response_model=JobResponse)
    def cancel_render_job(job_id: str) -> JobResponse:
        job = _job_or_404(state, job_id)
        with state.lock:
            if job["status"] in {"completed", "failed", "cancelled"}:
                return _job_response(job)
            state.cancel_events[job_id].set()
            if job["status"] == "queued":
                job["status"] = "cancelled"
        _log("render_job_cancel_requested", job_id=job_id)
        return _job_response(job)

    resolved_frontend = frontend_dist or os.environ.get("EPUB_CHAPTERS_FRONTEND_DIST")
    if resolved_frontend:
        mount_frontend(app, resolved_frontend)

    return app


def mount_frontend(app: FastAPI, frontend_dist: str | Path) -> None:
    dist = Path(frontend_dist).resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"frontend build not found at {index}")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{asset_path:path}", include_in_schema=False)
    def serve_frontend_asset(asset_path: str) -> FileResponse:
        requested = (dist / asset_path).resolve()
        if requested.is_file() and requested.is_relative_to(dist):
            return FileResponse(requested)
        return FileResponse(index)


def _run_render_job(state: ApiState, job_id: str, chapters: Sequence[Chapter], payload: RenderRequest) -> None:
    output_dir = state.render_root / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[ChapterAudio] = []
    cancel_event = state.cancel_events[job_id]
    try:
        with state.lock:
            state.jobs[job_id]["status"] = "running"
        engine = state.get_engine()
        options = payload.options.to_synth_options()
        for chapter in chapters:
            if cancel_event.is_set():
                _mark_job_cancelled(state, job_id)
                return
            with state.lock:
                state.jobs[job_id]["current_chapter_id"] = chapter.id
            chapter_dir = output_dir / f"{chapter.reading_order:04d}-{_safe_name(chapter.id)}"
            chapter_audio = engine.synthesize_chapters([chapter], chapter_dir, options=options)
            rendered.extend(_coerce_chapter_audio(chapter_audio))
            with state.lock:
                state.jobs[job_id]["completed_chapters"] += 1
            _log("render_chapter_completed", job_id=job_id, chapter_id=chapter.id)

        if cancel_event.is_set():
            _mark_job_cancelled(state, job_id)
            return

        output_path: Path | None = None
        if hasattr(engine, "mux_m4b"):
            output_path = output_dir / f"{payload.output_name}.m4b"
            engine.mux_m4b(rendered, output_path, work_dir=output_dir / "mux")
        elif rendered:
            output_path = rendered[-1].path

        with state.lock:
            state.jobs[job_id].update(
                {
                    "status": "completed",
                    "current_chapter_id": None,
                    "output_path": str(output_path) if output_path is not None else None,
                }
            )
        _log("render_job_completed", job_id=job_id, chapter_count=len(rendered))
    except Exception as exc:
        with state.lock:
            state.jobs[job_id].update({"status": "failed", "error": exc.__class__.__name__, "current_chapter_id": None})
        _log("render_job_failed", job_id=job_id, error=exc.__class__.__name__)


def _resolved_cors_origins() -> tuple[str, ...]:
    """Resolve the browser origins allowed to call the API.

    ``EPUB_CHAPTERS_API_CORS_ORIGINS`` is a comma-separated allow-list; when
    unset the documented localhost UI origins are used. A literal ``*`` is
    rejected so a deployment never accidentally opens the API to every origin.
    """
    raw = os.environ.get("EPUB_CHAPTERS_API_CORS_ORIGINS")
    if not raw:
        return DEFAULT_CORS_ORIGINS
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    if "*" in origins:
        raise ValueError("EPUB_CHAPTERS_API_CORS_ORIGINS must list explicit origins, not '*'")
    return origins or DEFAULT_CORS_ORIGINS


def configure_structured_logging() -> None:
    if getattr(configure_structured_logging, "_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    setattr(configure_structured_logging, "_configured", True)


def _log(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _validate_upload_metadata(file: UploadFile) -> None:
    filename = file.filename or ""
    if not filename.lower().endswith(".epub"):
        raise HTTPException(status_code=422, detail="file must use the .epub extension")
    if file.content_type not in {None, "", "application/epub+zip", "application/octet-stream", "application/x-zip-compressed"}:
        raise HTTPException(status_code=422, detail="file must be an EPUB upload")


def _copy_upload(source: SpooledTemporaryFile[bytes], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.seek(0)
    total = 0
    with destination.open("wb") as out:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EPUB_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="EPUB upload is too large")
            out.write(chunk)
    if total == 0:
        raise HTTPException(status_code=422, detail="EPUB upload cannot be empty")


def _book_or_404(state: ApiState, book_id: str) -> ChapterBook:
    with state.lock:
        book = state.books.get(book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="book not found")
    return book


def _job_or_404(state: ApiState, job_id: str) -> dict[str, Any]:
    with state.lock:
        job = state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="render job not found")
    return job


def _chapter_or_404(book: ChapterBook, chapter_id: str) -> Chapter:
    try:
        return next(chapter for chapter in book.chapters if chapter.id == chapter_id)
    except StopIteration as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chapter not found") from exc


def _chapter_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chapter not found")
    return HTTPException(status_code=422, detail=str(exc))


def _book_response(book_id: str, book: ChapterBook) -> BookResponse:
    return BookResponse(
        book_id=book_id,
        chapter_count=len(book.chapters),
        chapters=tuple(_chapter_response(chapter) for chapter in book.chapters),
    )


def _chapter_response(chapter: Chapter) -> ChapterResponse:
    return ChapterResponse(**asdict(chapter))


def _job_response(job: dict[str, Any]) -> JobResponse:
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        book_id=job["book_id"],
        total_chapters=job["total_chapters"],
        completed_chapters=job["completed_chapters"],
        current_chapter_id=job["current_chapter_id"],
        output_path=job["output_path"],
        error=job["error"],
    )


def _coerce_chapter_audio(value: object) -> list[ChapterAudio]:
    if isinstance(value, ChapterAudio):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        audio: list[ChapterAudio] = []
        for item in value:
            if isinstance(item, ChapterAudio):
                audio.append(item)
            elif is_dataclass(item) and hasattr(item, "path") and hasattr(item, "chapter"):
                audio.append(item)
            else:
                raise TypeError("synthesis engine returned unsupported chapter audio")
        return audio
    raise TypeError("synthesis engine returned unsupported chapter audio")


def _mark_job_cancelled(state: ApiState, job_id: str) -> None:
    with state.lock:
        state.jobs[job_id].update({"status": "cancelled", "current_chapter_id": None})
    _log("render_job_cancelled", job_id=job_id)


def _safe_name(value: str) -> str:
    normalized = normalize_text(value).lower()
    name = "".join(character if character.isalnum() else "-" for character in normalized)
    return "-".join(part for part in name.split("-") if part)[:80]


app = create_app()
