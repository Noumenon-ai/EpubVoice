from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from ebooklib import epub

from epub_chapters import ChapterBook, parse_epub, segment_sentences
from epub_chapters.parser import EpubParseError


def write_epub(path: Path, chapters: list[tuple[str, str]]) -> Path:
    book = epub.EpubBook()
    book.set_identifier("phase-1-test-book")
    book.set_title("Phase 1 Test Book")
    book.set_language("en")

    spine = ["nav"]
    toc = []
    for index, (title, body) in enumerate(chapters, start=1):
        item = epub.EpubHtml(
            title=title,
            file_name=f"chapter-{index}.xhtml",
            lang="en",
            uid=f"chapter-{index}",
        )
        item.content = f"<html><body><h1>{title}</h1>{body}</body></html>"
        book.add_item(item)
        spine.append(item)
        toc.append(item)

    book.toc = tuple(toc)
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)
    return path


def test_parse_epub_returns_ordered_normalized_chapters(tmp_path: Path) -> None:
    epub_path = write_epub(
        tmp_path / "book.epub",
        [
            ("Opening", "<p>A line-broken hyphen-\nated word. Next sentence.</p>"),
            ("Second", "<p>Another chapter with <strong>markup</strong>.</p>"),
        ],
    )

    chapters = parse_epub(epub_path)

    assert [chapter.title for chapter in chapters] == ["Opening", "Second"]
    assert [chapter.reading_order for chapter in chapters] == [0, 1]
    assert chapters[0].text == "A line-broken hyphenated word. Next sentence."
    assert chapters[0].sentences == ("A line-broken hyphenated word.", "Next sentence.")
    assert chapters[1].text == "Another chapter with markup."


def test_sentence_segmentation_handles_edge_without_terminal_punctuation() -> None:
    assert segment_sentences("One sentence. Last fragment") == ("One sentence.", "Last fragment")


def test_parse_epub_rejects_missing_or_empty_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_epub(tmp_path / "missing.epub")

    empty_path = write_epub(tmp_path / "empty.epub", [("Blank", "<p>   </p>")])
    with pytest.raises(EpubParseError):
        parse_epub(empty_path)


def test_parse_epub_rejects_corrupt_and_non_epub_files(tmp_path: Path) -> None:
    # Garbage bytes with an .epub extension must not leak ebooklib's internals.
    garbage = tmp_path / "garbage.epub"
    garbage.write_bytes(b"this is not an epub at all")
    with pytest.raises(EpubParseError):
        parse_epub(garbage)

    # A valid zip that lacks the EPUB container metadata.
    not_epub = tmp_path / "plain.epub"
    with zipfile.ZipFile(not_epub, "w") as archive:
        archive.writestr("hello.txt", "nope")
    with pytest.raises(EpubParseError):
        parse_epub(not_epub)


def test_chapter_book_merge_split_rename_and_exclude(tmp_path: Path) -> None:
    chapters = parse_epub(
        write_epub(
            tmp_path / "editable.epub",
            [
                ("One", "<p>Alpha sentence. Beta sentence.</p>"),
                ("Two", "<p>Gamma sentence.</p>"),
            ],
        )
    )
    book = ChapterBook(chapters)

    renamed = book.rename("chapter-1", " First Chapter ")
    assert renamed.title == "First Chapter"

    left, right = book.split("chapter-1", len("Alpha sentence."), second_title="Continuation")
    assert left.text == "Alpha sentence."
    assert right.title == "Continuation"
    assert right.text == "Beta sentence."
    assert [chapter.reading_order for chapter in book.chapters] == [0, 1, 2]

    merged = book.merge(left.id, right.id, title="Rejoined")
    assert merged.title == "Rejoined"
    assert merged.text == "Alpha sentence. Beta sentence."

    excluded = book.exclude("chapter-2")
    assert excluded.excluded is True
    assert [chapter.id for chapter in book.included()] == ["chapter-1"]


def test_chapter_book_validation_errors(tmp_path: Path) -> None:
    chapters = parse_epub(write_epub(tmp_path / "validation.epub", [("One", "<p>Alpha.</p>")]))
    book = ChapterBook(chapters)

    with pytest.raises(ValueError):
        book.rename("chapter-1", " ")
    with pytest.raises(ValueError):
        book.split("chapter-1", 0)
    with pytest.raises(KeyError):
        book.exclude("missing")
