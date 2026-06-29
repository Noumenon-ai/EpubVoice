from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    text: str
    reading_order: int
    sentences: tuple[str, ...] = field(default_factory=tuple)
    excluded: bool = False

    def with_changes(self, **changes: object) -> "Chapter":
        return replace(self, **changes)
