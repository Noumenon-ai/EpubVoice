from __future__ import annotations

import re
from html import unescape

_SENTENCE_RE = re.compile(
    r"""
    [^\s.!?]
    (?:
        [^.!?]|
        \.(?=\w)
    )*
    [.!?]+
    (?=\s+["'(\[]?[A-Z0-9]|\s*$|$)
    |
    [^\s.!?][^.!?]*$
    """,
    re.VERBOSE,
)


def normalize_text(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")

    text = unescape(raw_text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]*\n+[ \t]*", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def segment_sentences(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text)
    if not normalized:
        return ()
    sentences = tuple(match.group(0).strip() for match in _SENTENCE_RE.finditer(normalized))
    return sentences or (normalized,)
