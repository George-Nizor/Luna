"""Deterministic, punctuation-aware text chunking."""

from __future__ import annotations

import re

_STRONG_END = ".!?;:"


def _clean(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n[ \t]*\n[ \t]*(?:\n[ \t]*)+", "\n\n", normalized)
    return normalized.strip()


def _split_long_piece(piece: str, maximum: int) -> list[str]:
    if len(piece) <= maximum:
        return [piece]
    words = re.findall(r"\S+", piece)
    result: list[str] = []
    current = ""
    for word in words:
        if len(word) > maximum:
            if current:
                result.append(current)
                current = ""
            for index in range(0, len(word), maximum):
                result.append(word[index : index + maximum])
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= maximum:
            current = candidate
        else:
            result.append(current)
            current = word
    if current:
        result.append(current)
    return result


def chunk_text(text: str, target: int = 350, maximum: int = 500) -> list[str]:
    """Split text while preserving order and punctuation.

    A single uninterrupted token is split into bounded pieces as a practical
    safety measure; ordinary chunks never exceed ``maximum`` characters.
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")
    if target <= 0 or maximum <= 0 or target > maximum:
        raise ValueError("Invalid chunk size configuration.")
    cleaned = _clean(text)
    if not cleaned:
        raise ValueError("Text cannot be empty.")

    paragraphs = re.split(r"\n\n+", cleaned)
    units: list[str] = []
    for paragraph in paragraphs:
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        if not paragraph:
            continue
        # Keep sentence punctuation attached to its sentence, then fall back
        # to commas/whitespace later when a sentence is too large.
        sentences = re.findall(r".*?(?:[.!?;:](?=\s|$)|$)", paragraph)
        sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
        units.extend(sentences or [paragraph])

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for unit in units:
        if len(unit) > maximum:
            flush()
            # Prefer commas before the whitespace fallback.
            comma_parts = re.split(r"(?<=,\s)", unit)
            expanded: list[str] = []
            for part in comma_parts:
                expanded.extend(_split_long_piece(part.strip(), maximum))
            for part in expanded:
                if len(part) <= target and current:
                    candidate = f"{current} {part}"
                    if len(candidate) <= maximum:
                        current = candidate
                    else:
                        flush()
                        current = part
                else:
                    if current and len(current) + 1 + len(part) > maximum:
                        flush()
                    current = part
                if len(current) >= target:
                    flush()
            continue

        candidate = unit if not current else f"{current} {unit}"
        if current and len(candidate) > maximum:
            flush()
            current = unit
        elif len(candidate) <= target or not current:
            current = candidate
        else:
            flush()
            current = unit
        if len(current) >= target:
            flush()
    flush()

    return [chunk for chunk in chunks if chunk]
