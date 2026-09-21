from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import fitz


SHEET_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}\.\d{2})\b", re.I)


@dataclass(frozen=True)
class PdfPage:
    page_number: int
    text: str
    sheet: str | None


def _sheet_from_filename(path: Path) -> str | None:
    m = SHEET_RE.search(path.name)
    return m.group(1).upper() if m else None


def detect_sheet_id(text: str, *, filename: str | None = None) -> str | None:
    """Conservatively detect the drawing sheet represented by one PDF page.

    Single-sheet filenames win. For compiled sets, the title block is usually extracted late,
    so the last plausible sheet token in the tail of the page is preferred.
    """
    if filename:
        by_name = _sheet_from_filename(Path(filename))
        if by_name:
            return by_name
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tail = "\n".join(lines[-90:])
    candidates = [m.group(1).upper() for m in SHEET_RE.finditer(tail)]
    if not candidates:
        return None
    return candidates[-1]


def extract_pdf_pages(path: str | Path) -> tuple[PdfPage, ...]:
    path = Path(path)
    pages: list[PdfPage] = []
    single_sheet = _sheet_from_filename(path)
    doc = fitz.open(path)
    try:
        for number, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            sheet = single_sheet or detect_sheet_id(text)
            pages.append(PdfPage(number, text, sheet))
    finally:
        doc.close()
    return tuple(pages)


def extract_pdf_text(path: str | Path) -> str:
    return "\n".join(page.text for page in extract_pdf_pages(path))


def index_pages_by_sheet(pages: tuple[PdfPage, ...]) -> dict[str, PdfPage]:
    out: dict[str, PdfPage] = {}
    for page in pages:
        if page.sheet:
            out[page.sheet] = page
    return out
