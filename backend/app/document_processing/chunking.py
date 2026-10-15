"""Sentence and paragraph aware chunks with page and section provenance."""

import re
from dataclasses import dataclass

from app.document_processing.sections import SectionSegment


@dataclass(frozen=True)
class TextUnit:
    text: str
    page_number: int
    section: str | None
    paragraph_start: bool = False


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    page_start: int
    page_end: int
    section: str | None
    chunk_index: int
    character_count: int
    word_count: int


def _split_long_sentence(sentence: str, size: int) -> list[str]:
    if len(sentence) <= size:
        return [sentence]
    pieces: list[str] = []
    current: list[str] = []
    for word in sentence.split():
        if len(word) > size:
            if current:
                pieces.append(" ".join(current))
                current = []
            pieces.extend(word[index:index + size] for index in range(0, len(word), size))
            continue
        if current and len(" ".join(current + [word])) > size:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _units(segments: list[SectionSegment], size: int) -> list[TextUnit]:
    units: list[TextUnit] = []
    for segment in segments:
        for paragraph in segment.text.split("\n\n"):
            sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
            first = True
            for sentence in sentences:
                if not sentence:
                    continue
                for piece in _split_long_sentence(sentence, size):
                    units.append(TextUnit(piece, segment.page_number, segment.section, first))
                    first = False
    return units


def _render(units: list[TextUnit]) -> str:
    if not units:
        return ""
    parts = [units[0].text]
    for unit in units[1:]:
        parts.append("\n\n" if unit.paragraph_start else " ")
        parts.append(unit.text)
    return "".join(parts)


def _overlap(units: list[TextUnit], overlap_chars: int) -> list[TextUnit]:
    if overlap_chars == 0:
        return []
    result: list[TextUnit] = []
    for unit in reversed(units):
        result.insert(0, unit)
        if len(_render(result)) >= overlap_chars:
            break
    return result


def chunk_segments(segments: list[SectionSegment], size: int, overlap_chars: int) -> list[ChunkDraft]:
    if size <= 0 or overlap_chars < 0 or overlap_chars >= size:
        raise ValueError("Chunk size must exceed overlap")

    chunks: list[ChunkDraft] = []
    buffer: list[TextUnit] = []

    def emit() -> None:
        if not buffer:
            return
        text = _render(buffer)
        chunks.append(ChunkDraft(text, buffer[0].page_number, buffer[-1].page_number, buffer[0].section, len(chunks), len(text), len(text.split())))

    for unit in _units(segments, size):
        if buffer and unit.section != buffer[-1].section:
            emit()
            buffer = []
        if buffer and len(_render(buffer + [unit])) > size:
            emit()
            buffer = _overlap(buffer, overlap_chars)
            while buffer and len(_render(buffer + [unit])) > size:
                buffer.pop(0)
        buffer.append(unit)
    emit()
    return chunks
