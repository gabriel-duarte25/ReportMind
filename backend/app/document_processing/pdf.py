"""Extract unmodified text from each PDF page."""

from collections.abc import Iterator
from pathlib import Path

import pymupdf


class ProtectedPDFError(Exception):
    pass


def iter_pdf_pages(path: Path) -> Iterator[tuple[int, str]]:
    with pymupdf.open(str(path), filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ProtectedPDFError("PDF requires a password")
        for index in range(pdf.page_count):
            yield index + 1, pdf.load_page(index).get_text("text")
