"""Real-world EPUB robustness tests for chapter reading-order extraction.

These complement tests/test_epub.py and cover spine quirks that appear in
production EPUBs: navigation documents with non-"nav" ids and non-linear
spine items (footnotes, pop-up notes) that must stay out of the reading flow.
"""
from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from epub_chapters import parse_epub


def _build_book(tmp_path: Path) -> Path:
    book = epub.EpubBook()
    book.set_identifier("robustness-book")
    book.set_title("Robustness Book")
    book.set_language("en")

    chapter = epub.EpubHtml(title="Chapter One", file_name="c1.xhtml", uid="c1")
    chapter.content = (
        "<html><body><h1>Chapter One</h1>"
        "<p>The first real sentence. The second real sentence.</p>"
        "</body></html>"
    )

    notes = epub.EpubHtml(title="Notes", file_name="notes.xhtml", uid="notes")
    notes.content = (
        "<html><body><h1>Notes</h1><p>Non-linear footnote content.</p></body></html>"
    )

    # A navigation document that does NOT use the literal id "nav".
    custom_nav = epub.EpubNav(uid="toc-doc", file_name="toc.xhtml")

    book.add_item(chapter)
    book.add_item(notes)
    book.add_item(custom_nav)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Reading order: standard nav (skipped), the custom nav doc (must be skipped),
    # the real chapter, and a non-linear notes page (must be skipped).
    book.spine = ["nav", custom_nav, chapter, (notes, "no")]

    out = tmp_path / "robust.epub"
    epub.write_epub(str(out), book)
    return out


def test_navigation_documents_are_not_parsed_as_chapters(tmp_path: Path) -> None:
    chapters = parse_epub(_build_book(tmp_path))

    titles = [chapter.title for chapter in chapters]
    assert titles == ["Chapter One"]
    assert all("Non-linear" not in chapter.text for chapter in chapters)


def test_non_linear_spine_items_stay_out_of_reading_order(tmp_path: Path) -> None:
    chapters = parse_epub(_build_book(tmp_path))

    assert [chapter.reading_order for chapter in chapters] == [0]
    assert chapters[0].text == "The first real sentence. The second real sentence."
    assert all(chapter.title != "Notes" for chapter in chapters)
