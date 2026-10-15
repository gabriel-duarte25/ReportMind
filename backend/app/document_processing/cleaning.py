"""Conservative text cleanup; extracted source text remains unchanged in the database."""

import re
import unicodedata


def clean_text(raw_text: str) -> str:
    normalized = unicodedata.normalize("NFC", raw_text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ").replace("\u200b", "").replace("\u00ad", "")
    normalized = "".join(char for char in normalized if char in {"\n", "\t"} or unicodedata.category(char) != "Cc")

    paragraphs: list[str] = []
    current_lines: list[str] = []

    def finish_paragraph() -> None:
        if current_lines:
            paragraphs.append("\n".join(current_lines))
            current_lines.clear()

    for raw_line in normalized.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line:
            if current_lines and line[0].islower() and current_lines[-1][-1] not in ".!?:;":
                current_lines[-1] += " " + line
            else:
                current_lines.append(line)
        else:
            finish_paragraph()
    finish_paragraph()
    return "\n\n".join(paragraphs)
