from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

import pdfplumber


@dataclass(frozen=True)
class QuoteHeader:
    number: str | None = None
    date: str | None = None
    description: str | None = None
    terms: str | None = None
    rep: str | None = None


@dataclass(frozen=True)
class QuoteLine:
    item: int
    description: str
    quantity: float
    each: float
    code: str
    tax_each: float
    amount: float
    sheet_refs: tuple[str, ...] = field(default_factory=tuple)
    elevation_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def calculated_amount(self) -> float:
        return round(self.quantity * (self.each + self.tax_each), 2)

    @property
    def amount_matches_display(self) -> bool:
        return abs(self.calculated_amount - self.amount) <= 0.01


@dataclass(frozen=True)
class QuoteDocument:
    header: QuoteHeader
    lines: tuple[QuoteLine, ...]
    quote_total: float | None
    notes: str

    @property
    def calculated_total(self) -> float:
        return round(sum(line.amount for line in self.lines), 2)

    @property
    def total_matches_display(self) -> bool | None:
        if self.quote_total is None:
            return None
        return abs(self.calculated_total - self.quote_total) <= 0.01

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["calculated_total"] = self.calculated_total
        data["total_matches_display"] = self.total_matches_display
        for row, line in zip(data["lines"], self.lines):
            row["calculated_amount"] = line.calculated_amount
            row["amount_matches_display"] = line.amount_matches_display
        return data


_ITEM_HEADER_RE = re.compile(r"Item\s*Description\s+Qty\s+Each\s*Code\s*Tax\s+Each\s*Amount", re.I)
_LINE_WITH_PRICE_RE = re.compile(
    r"(?m)^\s*(?P<item>\d+)\s+(?P<desc>.*?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+(?P<each>\d+\.\d{2})\s+"
    r"(?P<code>[A-Z]{1,8})\s+(?P<tax>\d+\.\d{2})\s+(?P<amount>\d+\.\d{2})\s*$"
)
_SHEET_RE = re.compile(r"\bA\d{1,2}\.\d{2}\b", re.I)
_ELEVATION_RE = re.compile(r"\bElevations?\s+([0-9]+(?:\s*/\s*[0-9]+)*)", re.I)
_HEADER_RE = re.compile(
    r"(?m)^\s*(?P<number>\d{4,})\s+(?P<date>[A-Z]{3}\s+\d{1,2}\s+\d{4})\s+"
    r"(?P<description>.+?)\s+(?P<terms>\d+(?:/\d+){1,5})\s+(?P<rep>[A-Z]{1,5})\s*$"
)
_QUOTE_TOTAL_RE = re.compile(r"General\s+Notes\s+Quote\s+Total[\s\S]{0,350}?\b(\d{3,}\.[0-9]{2})\b", re.I)
_FOOTER_RE = re.compile(r"(?im)^JEFFREY TROTT INDUSTRIES.*$|^CONTRACTORS LICENSE.*$")
_PAGE_HEADER_RE = re.compile(r"(?im)^QUOTE\s+\d+.*$|^\(Page\s+\d+\)\s*$")


def _clean_description(text: str) -> str:
    return " ".join(text.replace("\u201c", '"').replace("\u201d", '"').split())


def _references(description: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    sheets = tuple(dict.fromkeys(m.group(0).upper() for m in _SHEET_RE.finditer(description)))
    elevations: list[str] = []
    for match in _ELEVATION_RE.finditer(description):
        elevations.extend(x.strip() for x in match.group(1).split("/") if x.strip())
    return sheets, tuple(dict.fromkeys(elevations))


def _header(text: str) -> QuoteHeader:
    match = _HEADER_RE.search(text)
    if not match:
        return QuoteHeader()
    return QuoteHeader(**{k: _clean_description(v) for k, v in match.groupdict().items()})


def parse_jti_quote_text(text: str) -> QuoteDocument:
    """Parse layout-preserving text from a JTI quotation."""
    text = _FOOTER_RE.sub("", text)
    text = _PAGE_HEADER_RE.sub("", text)
    header = _header(text)
    matches = list(_ITEM_HEADER_RE.finditer(text))
    lines: list[QuoteLine] = []

    for idx, marker in enumerate(matches):
        start = marker.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        if "General Notes" in block:
            block = block.split("General Notes", 1)[0]
        first = _LINE_WITH_PRICE_RE.search(block)
        if not first:
            continue
        continuation = block[first.end():]
        continuation = re.split(r"\bGeneral\s+Notes\b", continuation, maxsplit=1, flags=re.I)[0]
        desc = _clean_description(first.group("desc") + " " + continuation)
        sheets, elevations = _references(desc)
        lines.append(
            QuoteLine(
                item=int(first.group("item")),
                description=desc,
                quantity=float(first.group("qty")),
                each=float(first.group("each")),
                code=first.group("code"),
                tax_each=float(first.group("tax")),
                amount=float(first.group("amount")),
                sheet_refs=sheets,
                elevation_refs=elevations,
            )
        )

    total_match = _QUOTE_TOTAL_RE.search(text)
    quote_total = float(total_match.group(1)) if total_match else None
    notes = ""
    notes_match = re.search(
        r"General\s+Notes\s+Quote\s+Total(?P<notes>[\s\S]*?)(?:Prices are good|$)", text, re.I
    )
    if notes_match:
        notes = _clean_description(re.sub(r"\b\d{3,}\.\d{2}\b", "", notes_match.group("notes"), count=1))
    return QuoteDocument(header=header, lines=tuple(lines), quote_total=quote_total, notes=notes)


def parse_jti_quote_pdf(path: str | Path) -> QuoteDocument:
    # JTI's quote PDF is columnar; layout-preserving extraction is materially more reliable
    # than generic PDF text extraction for Qty/Each/Code/Tax/Amount.
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
    return parse_jti_quote_text("\n".join(chunks))
