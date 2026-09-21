from __future__ import annotations

from dataclasses import dataclass, field
import re


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


_ITEM_HEADER_RE = re.compile(
    r"Item\s+Description\s+Qty\s+Each\s+Code\s+Tax\s+Each\s+Amount",
    re.I,
)

# PDF text extraction normally emits the sell fields on one line after the multiline
# description. Requiring 2 decimal places on monetary values avoids swallowing common
# drawing dimensions into the pricing row.
_PRICE_ROW_RE = re.compile(
    r"(?m)^\s*(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?P<each>\d+\.\d{2})\s+"
    r"(?P<code>[A-Z]{1,8})\s+"
    r"(?P<tax>\d+\.\d{2})\s+"
    r"(?P<amount>\d+\.\d{2})\s*$"
)

_SHEET_RE = re.compile(r"\bA\d{1,2}\.\d{2}\b", re.I)
_ELEVATION_RE = re.compile(
    r"\bElevations?\s+([0-9]+(?:\s*/\s*[0-9]+)*)",
    re.I,
)
_HEADER_RE = re.compile(
    r"(?m)^\s*(?P<number>\d{4,})\s+"
    r"(?P<date>[A-Z]{3}\s+\d{1,2}\s+\d{4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<terms>\d+(?:/\d+){1,5})\s+"
    r"(?P<rep>[A-Z]{1,5})\s*$"
)
_QUOTE_TOTAL_RE = re.compile(r"Quote\s+Total[\s\S]{0,180}?\b(\d+\.\d{2})\b", re.I)


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
    """Parse text extracted from a JTI-style quotation PDF.

    The parser is intentionally conservative: a line item is accepted only when a numbered
    description is followed by a row matching the displayed Qty/Each/Code/Tax Each/Amount
    structure. This keeps drawing dimensions and detail numbers from becoming prices.
    """
    header = _header(text)
    matches = list(_ITEM_HEADER_RE.finditer(text))
    lines: list[QuoteLine] = []

    for idx, match in enumerate(matches):
        block_start = match.end()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[block_start:block_end]

        item_match = re.match(r"\s*(\d+)\s+", block)
        if not item_match:
            continue
        item = int(item_match.group(1))
        price_match = _PRICE_ROW_RE.search(block, item_match.end())
        if not price_match:
            continue

        description = _clean_description(block[item_match.end():price_match.start()])
        sheets, elevations = _references(description)
        lines.append(
            QuoteLine(
                item=item,
                description=description,
                quantity=float(price_match.group("qty")),
                each=float(price_match.group("each")),
                code=price_match.group("code"),
                tax_each=float(price_match.group("tax")),
                amount=float(price_match.group("amount")),
                sheet_refs=sheets,
                elevation_refs=elevations,
            )
        )

    total_match = _QUOTE_TOTAL_RE.search(text)
    quote_total = float(total_match.group(1)) if total_match else None

    notes = ""
    notes_match = re.search(r"General\s+Notes(?P<notes>[\s\S]*?)(?:Prices are good|$)", text, re.I)
    if notes_match:
        notes = _clean_description(notes_match.group("notes"))

    return QuoteDocument(
        header=header,
        lines=tuple(lines),
        quote_total=quote_total,
        notes=notes,
    )
