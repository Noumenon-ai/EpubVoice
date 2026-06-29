from __future__ import annotations

from collections.abc import Iterable

from .models import Chapter
from .normalizer import normalize_text, segment_sentences


class ChapterBook:
    def __init__(self, chapters: Iterable[Chapter]):
        self._chapters = list(chapters)
        if not self._chapters:
            raise ValueError("ChapterBook requires at least one chapter")
        self._ensure_unique_ids()
        self._renumber()

    @property
    def chapters(self) -> tuple[Chapter, ...]:
        return tuple(self._chapters)

    def rename(self, chapter_id: str, title: str) -> Chapter:
        normalized_title = normalize_text(title)
        if not normalized_title:
            raise ValueError("chapter title cannot be empty")
        index = self._index_for(chapter_id)
        chapter = self._chapters[index].with_changes(title=normalized_title)
        self._chapters[index] = chapter
        return chapter

    def edit_text(self, chapter_id: str, text: str) -> Chapter:
        normalized_text = normalize_text(text)
        if not normalized_text:
            raise ValueError("chapter text cannot be empty")
        index = self._index_for(chapter_id)
        chapter = self._chapters[index].with_changes(
            text=normalized_text,
            sentences=segment_sentences(normalized_text),
        )
        self._chapters[index] = chapter
        return chapter

    def exclude(self, chapter_id: str, excluded: bool = True) -> Chapter:
        index = self._index_for(chapter_id)
        chapter = self._chapters[index].with_changes(excluded=bool(excluded))
        self._chapters[index] = chapter
        return chapter

    def merge(self, first_chapter_id: str, second_chapter_id: str, title: str | None = None) -> Chapter:
        first_index = self._index_for(first_chapter_id)
        second_index = self._index_for(second_chapter_id)
        if abs(first_index - second_index) != 1:
            raise ValueError("only adjacent chapters can be merged")
        left_index, right_index = sorted((first_index, second_index))
        left = self._chapters[left_index]
        right = self._chapters[right_index]
        merged_text = normalize_text(f"{left.text}\n\n{right.text}")
        merged_title = normalize_text(title) if title is not None else f"{left.title} / {right.title}"
        if not merged_title:
            raise ValueError("merged chapter title cannot be empty")
        merged = Chapter(
            id=left.id,
            title=merged_title,
            text=merged_text,
            reading_order=left.reading_order,
            sentences=segment_sentences(merged_text),
            excluded=left.excluded and right.excluded,
        )
        self._chapters[left_index : right_index + 1] = [merged]
        self._renumber()
        return self._chapters[left_index]

    def split(
        self,
        chapter_id: str,
        offset: int,
        first_title: str | None = None,
        second_title: str | None = None,
    ) -> tuple[Chapter, Chapter]:
        index = self._index_for(chapter_id)
        original = self._chapters[index]
        if not isinstance(offset, int):
            raise TypeError("offset must be an integer")
        if offset <= 0 or offset >= len(original.text):
            raise ValueError("offset must be inside chapter text boundaries")

        left_text = normalize_text(original.text[:offset])
        right_text = normalize_text(original.text[offset:])
        if not left_text or not right_text:
            raise ValueError("split offset must leave text on both sides")

        left_title = normalize_text(first_title) if first_title is not None else original.title
        right_title = normalize_text(second_title) if second_title is not None else f"{original.title} (Part 2)"
        if not left_title or not right_title:
            raise ValueError("split chapter titles cannot be empty")

        left = Chapter(
            id=original.id,
            title=left_title,
            text=left_text,
            reading_order=original.reading_order,
            sentences=segment_sentences(left_text),
            excluded=original.excluded,
        )
        right = Chapter(
            id=self._next_split_id(original.id),
            title=right_title,
            text=right_text,
            reading_order=original.reading_order + 1,
            sentences=segment_sentences(right_text),
            excluded=original.excluded,
        )
        self._chapters[index : index + 1] = [left, right]
        self._renumber()
        return self._chapters[index], self._chapters[index + 1]

    def included(self) -> tuple[Chapter, ...]:
        return tuple(chapter for chapter in self._chapters if not chapter.excluded)

    def _index_for(self, chapter_id: str) -> int:
        for index, chapter in enumerate(self._chapters):
            if chapter.id == chapter_id:
                return index
        raise KeyError(f"unknown chapter id: {chapter_id}")

    def _ensure_unique_ids(self) -> None:
        ids = [chapter.id for chapter in self._chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("chapter ids must be unique")

    def _next_split_id(self, base_id: str) -> str:
        existing = {chapter.id for chapter in self._chapters}
        suffix = 2
        while f"{base_id}-part-{suffix}" in existing:
            suffix += 1
        return f"{base_id}-part-{suffix}"

    def _renumber(self) -> None:
        self._chapters = [
            chapter.with_changes(reading_order=index)
            for index, chapter in enumerate(self._chapters)
        ]
