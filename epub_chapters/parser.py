from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT
from ebooklib import epub

from .models import Chapter
from .normalizer import normalize_text, segment_sentences


class EpubParseError(ValueError):
    pass


def parse_epub(path: str | Path) -> list[Chapter]:
    epub_path = Path(path)
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)
    if not epub_path.is_file():
        raise EpubParseError(f"EPUB path is not a file: {epub_path}")

    # ebooklib surfaces malformed archives as a grab-bag of exceptions
    # (EpubException for bad zips, KeyError for a missing OPF/container,
    # lxml errors for unparsable XML). Normalize them to EpubParseError so
    # callers have a single failure type to catch.
    try:
        book = epub.read_epub(str(epub_path))
    except FileNotFoundError:
        raise
    except (epub.EpubException, zipfile.BadZipFile, KeyError) as exc:
        raise EpubParseError(f"Not a readable EPUB file: {epub_path} ({exc})") from exc
    except Exception as exc:  # pragma: no cover - defensive catch-all
        raise EpubParseError(f"Failed to read EPUB file: {epub_path} ({exc})") from exc

    chapters: list[Chapter] = []

    for item in _iter_spine_documents(book):
        title, text = _extract_document_content(item.get_content())
        if not text:
            continue
        reading_order = len(chapters)
        chapters.append(
            Chapter(
                id=f"chapter-{reading_order + 1}",
                title=title or _fallback_title(item.get_name(), reading_order),
                text=text,
                reading_order=reading_order,
                sentences=segment_sentences(text),
            )
        )

    if not chapters:
        raise EpubParseError(f"No readable chapter documents found in {epub_path}")

    return chapters


def _iter_spine_documents(book: epub.EpubBook) -> Iterable[epub.EpubHtml]:
    seen: set[str] = set()
    for entry in book.spine:
        if isinstance(entry, tuple):
            item_id = entry[0]
            linear = entry[1] if len(entry) > 1 else "yes"
        else:
            item_id = entry
            linear = "yes"

        # Non-linear spine items (footnotes, pop-up notes, etc.) are not part of
        # the main reading flow and must not enter the chapter reading order.
        if isinstance(linear, str) and linear.strip().lower() == "no":
            continue
        if item_id == "nav" or item_id in seen:
            continue
        seen.add(item_id)

        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        # The EPUB3 navigation document is a table of contents, not a chapter,
        # even when it carries a non-"nav" id.
        if isinstance(item, epub.EpubNav) or _has_nav_property(item):
            continue
        yield item


def _has_nav_property(item: epub.EpubHtml) -> bool:
    properties = getattr(item, "properties", None) or ()
    return any(str(prop).strip().lower() == "nav" for prop in properties)


def _extract_document_content(content: bytes) -> tuple[str, str]:
    soup = BeautifulSoup(content, "lxml")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    body = soup.body or soup
    heading = body.find(["h1", "h2", "h3", "title"])
    title = normalize_text(heading.get_text(" ")) if heading else ""
    text = normalize_text(body.get_text("\n"))
    if title and text.startswith(title):
        text = text[len(title) :].strip()
    return title, text


def _fallback_title(name: str, reading_order: int) -> str:
    stem = Path(name).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else f"Chapter {reading_order + 1}"
