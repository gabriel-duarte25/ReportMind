"""Deterministic section heading detection, independent from PDF extraction."""

import re
import unicodedata
from dataclasses import dataclass

from app.document_processing.cleaning import clean_text

HEADINGS = {
    "abstract": "Abstract",
    "resumo": "Resumo",
    "introduction": "Introduction",
    "introducao": "Introdução",
    "methodology": "Methodology",
    "metodologia": "Metodologia",
    "results": "Results",
    "resultados": "Resultados",
    "discussion": "Discussion",
    "discussao": "Discussão",
    "conclusion": "Conclusion",
    "conclusao": "Conclusão",
    "references": "References",
    "referencias": "Referências",
}


@dataclass(frozen=True)
class SectionSegment:
    page_number: int
    section: str | None
    text: str


def detect_heading(line: str) -> str | None:
    candidate = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+", "", line.strip(), flags=re.IGNORECASE)
    candidate = candidate.strip(" .:-\t")
    normalized = "".join(char for char in unicodedata.normalize("NFKD", candidate.casefold()) if not unicodedata.combining(char))
    return HEADINGS.get(normalized)


def split_page_sections(raw_text: str, page_number: int, current_section: str | None) -> tuple[list[SectionSegment], str | None]:
    segments: list[SectionSegment] = []
    lines: list[str] = []

    def append_segment() -> None:
        text = clean_text("\n".join(lines))
        if text:
            segments.append(SectionSegment(page_number, current_section, text))

    for line in raw_text.splitlines():
        heading = detect_heading(line)
        if heading:
            if lines:
                append_segment()
            lines = [line]
            current_section = heading
        else:
            lines.append(line)
    if lines:
        append_segment()
    return segments, current_section
