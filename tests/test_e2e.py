from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

from ebooklib import epub

from epub_chapters.parser import parse_epub
from epub_chapters.synth import ChatterboxSynthesizer


class TinyVoice:
    sr = 8000

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, text: str) -> list[float]:
        self.prompts.append(text)
        frames = self.sr // 3
        return [math.sin(index / 18.0) * 0.15 for index in range(frames)]


def test_tiny_epub_renders_to_valid_chapterized_m4b(tmp_path: Path) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for the e2e smoke test"
    assert shutil.which("ffprobe"), "ffprobe is required for the e2e smoke test"

    epub_path = _write_tiny_epub(tmp_path / "tiny.epub")
    chapters = parse_epub(epub_path)
    voice = TinyVoice()
    synth = ChatterboxSynthesizer(model=voice)

    build = synth.build_m4b(
        chapters,
        tmp_path / "tiny.m4b",
        work_dir=tmp_path / "work",
    )

    assert build.output_path.is_file()
    assert build.output_path.stat().st_size > 0
    assert voice.prompts == [
        "A clock ticks beside the microphone.",
        "The page turns softly in the booth.",
    ]

    probe = _ffprobe(build.output_path)
    assert probe["format"]["format_name"].split(",")[0] == "mov"
    assert len(probe["chapters"]) == 2
    assert [chapter["tags"]["title"] for chapter in probe["chapters"]] == ["Opening", "Second Room"]


def _ffprobe(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_chapters",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _write_tiny_epub(path: Path) -> Path:
    book = epub.EpubBook()
    book.set_identifier("tiny-e2e-book")
    book.set_title("Tiny Studio Book")
    book.set_language("en")

    chapters = []
    for index, (title, body) in enumerate(
        [
            ("Opening", "A clock ticks beside the microphone."),
            ("Second Room", "The page turns softly in the booth."),
        ],
        start=1,
    ):
        item = epub.EpubHtml(title=title, file_name=f"chapter-{index}.xhtml", uid=f"chapter-{index}")
        item.content = f"<html><body><h1>{title}</h1><p>{body}</p></body></html>"
        book.add_item(item)
        chapters.append(item)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)
    return path
