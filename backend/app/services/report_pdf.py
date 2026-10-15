"""Render generated Markdown reports as polished PDF documents."""

from __future__ import annotations

import html
import io
import re
from datetime import datetime, timezone

import pymupdf


REPORT_CSS = """
* { box-sizing: border-box; }
body { font-family: sans-serif; color: #172033; font-size: 10.5pt; line-height: 1.48; }
h1 { color: #102a56; font-size: 24pt; line-height: 1.12; margin: 0 0 18pt; padding-bottom: 10pt; border-bottom: 2pt solid #2878ee; }
h2 { color: #173a70; font-size: 15pt; margin: 20pt 0 8pt; }
h3 { color: #22538f; font-size: 12pt; margin: 15pt 0 6pt; }
p { margin: 0 0 8pt; }
ul, ol { margin: 3pt 0 10pt 18pt; padding: 0; }
li { margin: 0 0 4pt; }
strong { color: #102a56; }
table { width: 100%; border-collapse: collapse; margin: 10pt 0 16pt; font-size: 8.2pt; }
th { background: #143e78; color: white; font-weight: bold; text-align: left; padding: 6pt; border: 0.5pt solid #466b9b; }
td { padding: 5.5pt 6pt; vertical-align: top; border: 0.5pt solid #cbd7e8; }
tr:nth-child(even) td { background: #f2f6fb; }
code { font-family: monospace; font-size: 9pt; background: #edf3fb; color: #173a70; }
"""


def _inline_markdown(value: str) -> str:
    escaped = html.escape(value.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    index = 0
    open_list: str | None = None

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            output.append(f"</{open_list}>")
            open_list = None

    while index < len(lines):
        raw = lines[index]
        line = raw.strip()
        if not line:
            close_list()
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines) and _is_table_separator(lines[index + 1].strip()):
            close_list()
            headers = _table_cells(line)
            output.append("<table><thead><tr>" + "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = _table_cells(lines[index])
                if not _is_table_separator(lines[index].strip()):
                    cells += [""] * max(0, len(headers) - len(cells))
                    output.append("<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in cells[:len(headers)]) + "</tr>")
                index += 1
            output.append("</tbody></table>")
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
            index += 1
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or numbered:
            wanted = "ul" if bullet else "ol"
            if open_list != wanted:
                close_list()
                output.append(f"<{wanted}>")
                open_list = wanted
            output.append(f"<li>{_inline_markdown((bullet or numbered).group(1))}</li>")
            index += 1
            continue

        close_list()
        paragraph = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate or candidate.startswith(("#", "|", "- ", "* ")) or re.match(r"^\d+\.\s+", candidate):
                break
            paragraph.append(candidate)
            index += 1
        output.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")

    close_list()
    return "<main>" + "".join(output) + "</main>"


def render_report_pdf(title: str, content: str) -> bytes:
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page_rect = pymupdf.paper_rect("a4")
    content_rect = page_rect + (46, 58, -46, -48)
    story = pymupdf.Story(html=markdown_to_html(content), user_css=REPORT_CSS)
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()

    document = pymupdf.open(stream=buffer.getvalue(), filetype="pdf")
    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    for page_number, page in enumerate(document, start=1):
        page.draw_rect(pymupdf.Rect(0, 0, page.rect.width, 7), color=(0.10, 0.35, 0.78), fill=(0.10, 0.35, 0.78))
        page.insert_text((46, 34), "REPORTMIND", fontsize=8.5, fontname="hebo", color=(0.08, 0.24, 0.47))
        page.insert_textbox(
            pymupdf.Rect(250, 23, page.rect.width - 46, 40),
            title[:70],
            fontsize=7.5,
            fontname="helv",
            color=(0.35, 0.42, 0.52),
            align=pymupdf.TEXT_ALIGN_RIGHT,
        )
        page.draw_line((46, page.rect.height - 32), (page.rect.width - 46, page.rect.height - 32), color=(0.80, 0.85, 0.91), width=0.5)
        page.insert_text((46, page.rect.height - 17), f"Gerado em {generated}", fontsize=7.5, color=(0.40, 0.46, 0.55))
        page.insert_textbox(
            pymupdf.Rect(350, page.rect.height - 26, page.rect.width - 46, page.rect.height - 10),
            f"Página {page_number} de {document.page_count}",
            fontsize=7.5,
            color=(0.40, 0.46, 0.55),
            align=pymupdf.TEXT_ALIGN_RIGHT,
        )
    result = document.tobytes(garbage=4, deflate=True)
    document.close()
    return result
