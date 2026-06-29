from __future__ import annotations

import time
import wave
from pathlib import Path
from typing import Sequence

from ebooklib import epub
from fastapi.testclient import TestClient

from epub_chapters.api import create_app
from epub_chapters.models import Chapter
from epub_chapters.synth import ChapterAudio


class StubEngine:
    def __init__(self, wav_fixture: Path) -> None:
        self.wav_fixture = wav_fixture
        self.preview_calls: list[dict[str, object]] = []
        self.chapter_calls: list[dict[str, object]] = []
        self.mux_calls: list[dict[str, object]] = []

    def synthesize_preview(self, output_path: Path, *, sample_line: str, options: object) -> bytes:
        self.preview_calls.append({"sample_line": sample_line, "options": options})
        output_path.write_bytes(self.wav_fixture.read_bytes())
        return self.wav_fixture.read_bytes()

    def synthesize_chapters(
        self,
        chapters: Sequence[Chapter],
        output_dir: Path,
        *,
        options: object,
    ) -> tuple[ChapterAudio, ...]:
        self.chapter_calls.append({"chapters": [chapter.id for chapter in chapters], "options": options})
        output_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[ChapterAudio] = []
        for chapter in chapters:
            path = output_dir / f"{chapter.id}.wav"
            path.write_bytes(self.wav_fixture.read_bytes())
            rendered.append(ChapterAudio(chapter=chapter, path=path, duration_ms=100))
        return tuple(rendered)

    def mux_m4b(self, chapter_wavs: Sequence[ChapterAudio], output_path: Path, *, work_dir: Path, cover_path: Path | None = None) -> object:
        self.mux_calls.append({"chapters": [audio.chapter.id for audio in chapter_wavs], "output_path": output_path})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"m4b")
        return object()


def test_health_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_configured_ui_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))

    response = client.get("/health", headers={"Origin": "http://127.0.0.1:4322"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4322"


def test_cors_rejects_unknown_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))

    response = client.get("/health", headers={"Origin": "http://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_env_override_rejects_wildcard(tmp_path: Path, monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("EPUB_CHAPTERS_API_CORS_ORIGINS", "*")
    with pytest.raises(ValueError):
        create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data")


def test_upload_epub_and_get_edit_chapter_model(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))
    epub_path = _write_epub(tmp_path / "book.epub")

    upload = client.post(
        "/epubs",
        files={"file": ("book.epub", epub_path.read_bytes(), "application/epub+zip")},
    )

    assert upload.status_code == 201
    body = upload.json()
    assert body["chapter_count"] == 2
    book_id = body["book_id"]
    assert body["chapters"][0]["title"] == "Opening"

    chapter = client.get(f"/books/{book_id}/chapters/chapter-1")
    assert chapter.status_code == 200
    assert chapter.json()["text"] == "First sentence."

    edited = client.patch(
        f"/books/{book_id}/chapters/chapter-1",
        json={"title": " Revised Opening ", "text": "Updated sentence. Second update.", "excluded": True},
    )
    assert edited.status_code == 200
    assert edited.json()["title"] == "Revised Opening"
    assert edited.json()["sentences"] == ["Updated sentence.", "Second update."]
    assert edited.json()["excluded"] is True

    listed = client.get(f"/books/{book_id}/chapters")
    assert listed.status_code == 200
    assert listed.json()[0]["reading_order"] == 0


def test_upload_rejects_non_epub_and_missing_book_returns_404(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))

    rejected = client.post(
        "/epubs",
        files={"file": ("notes.txt", b"not epub", "text/plain")},
    )

    assert rejected.status_code == 422
    assert client.get("/books/missing/chapters/chapter-1").status_code == 404


def test_tts_parameters_include_ranges_and_defaults(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))

    response = client.get("/tts/parameters")

    assert response.status_code == 200
    parameters = {item["name"]: item for item in response.json()}
    assert parameters["temperature"]["minimum"] == 0.0
    assert parameters["temperature"]["maximum"] == 5.0
    assert parameters["cfg_weight"]["default"] == 0.5
    assert parameters["seed"]["nullable"] is True


def test_voice_preview_validates_parameters_and_returns_wav(tmp_path: Path) -> None:
    engine = StubEngine(_write_wav(tmp_path / "voice.wav"))
    client = TestClient(create_app(engine=engine, storage_root=tmp_path / "data"))

    response = client.post(
        "/tts/preview",
        json={"sample_line": " Preview line. ", "options": {"temperature": 0.9, "seed": 10}},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == (tmp_path / "voice.wav").read_bytes()
    assert engine.preview_calls[0]["sample_line"] == "Preview line."

    invalid = client.post("/tts/preview", json={"sample_line": "ok", "options": {"temperature": 9.0}})
    assert invalid.status_code == 422


def test_render_job_tracks_progress_and_completes(tmp_path: Path) -> None:
    engine = StubEngine(_write_wav(tmp_path / "voice.wav"))
    client = TestClient(create_app(engine=engine, storage_root=tmp_path / "data"))
    book_id = _upload_book(client, tmp_path)

    started = client.post(
        "/render-jobs",
        json={"book_id": book_id, "output_name": "My Book", "options": {"cfg_weight": 0.4}},
    )

    assert started.status_code == 202
    job_id = started.json()["job_id"]
    job = _wait_for_job(client, job_id)
    assert job["status"] == "completed"
    assert job["total_chapters"] == 2
    assert job["completed_chapters"] == 2
    assert job["output_path"].endswith("my-book.m4b")
    assert engine.chapter_calls == [
        {"chapters": ["chapter-1"], "options": engine.chapter_calls[0]["options"]},
        {"chapters": ["chapter-2"], "options": engine.chapter_calls[1]["options"]},
    ]
    assert engine.mux_calls[0]["chapters"] == ["chapter-1", "chapter-2"]


def test_render_job_rejects_empty_cart_like_no_included_chapters(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))
    book_id = _upload_book(client, tmp_path)
    client.patch(f"/books/{book_id}/chapters/chapter-1", json={"excluded": True})
    client.patch(f"/books/{book_id}/chapters/chapter-2", json={"excluded": True})

    response = client.post("/render-jobs", json={"book_id": book_id})

    assert response.status_code == 422
    assert "included chapter" in response.json()["detail"]


def test_render_job_cancel_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app(engine=StubEngine(_write_wav(tmp_path / "voice.wav")), storage_root=tmp_path / "data"))
    book_id = _upload_book(client, tmp_path)
    started = client.post("/render-jobs", json={"book_id": book_id})

    response = client.post(f"/render-jobs/{started.json()['job_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] in {"queued", "running", "completed", "cancelled"}


def test_engine_is_constructed_once_across_requests(tmp_path: Path) -> None:
    engine = StubEngine(_write_wav(tmp_path / "voice.wav"))
    builds = {"count": 0}

    def factory() -> StubEngine:
        builds["count"] += 1
        return engine

    client = TestClient(create_app(engine_factory=factory, storage_root=tmp_path / "data"))
    book_id = _upload_book(client, tmp_path)

    preview = client.post("/tts/preview", json={"sample_line": "Voice check.", "options": {}})
    assert preview.status_code == 200
    started = client.post("/render-jobs", json={"book_id": book_id})
    assert started.status_code == 202
    job = _wait_for_job(client, started.json()["job_id"])

    assert job["status"] == "completed"
    assert builds["count"] == 1


def _upload_book(client: TestClient, tmp_path: Path) -> str:
    epub_path = _write_epub(tmp_path / f"{time.time_ns()}.epub")
    response = client.post(
        "/epubs",
        files={"file": ("book.epub", epub_path.read_bytes(), "application/epub+zip")},
    )
    assert response.status_code == 201
    return response.json()["book_id"]


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(100):
        response = client.get(f"/render-jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.01)
    raise AssertionError("render job did not finish")


def _write_epub(path: Path) -> Path:
    book = epub.EpubBook()
    book.set_identifier("api-test-book")
    book.set_title("API Test Book")
    book.set_language("en")

    chapters = []
    for index, (title, body) in enumerate(
        [
            ("Opening", "<p>First sentence.</p>"),
            ("Second", "<p>Another sentence.</p>"),
        ],
        start=1,
    ):
        item = epub.EpubHtml(title=title, file_name=f"chapter-{index}.xhtml", uid=f"chapter-{index}")
        item.content = f"<html><body><h1>{title}</h1>{body}</body></html>"
        book.add_item(item)
        chapters.append(item)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)
    return path


def _write_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(1000)
        wav.writeframes(b"\x00\x00" * 100)
    return path
