from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from auto_bid_builder.extract.signals import extract_signals
from auto_bid_builder.ingest.pdf import extract_pdf_pages

_SCOPE_TERMS = re.compile(r"\b(millwork|cabinet|casework|shelv(?:e|es|ing)|reception desk|counter|wood veneer|cladding|locker|wood beam|banquette|panel)\b", re.I)
_BY_OTHERS = re.compile(r"\b(by others|not included|electrical subcontractor|GCs?\s+electrical)\b", re.I)


@dataclass(frozen=True)
class ScopePage:
    source: str
    page: int
    sheet: str | None
    relevance_score: int
    scope_terms: tuple[str, ...]
    signals: tuple[dict[str, Any], ...]
    by_others_mentions: tuple[str, ...]


def scan_pdf(path: str | Path) -> tuple[ScopePage, ...]:
    path = Path(path)
    rows: list[ScopePage] = []
    for page in extract_pdf_pages(path):
        terms = tuple(dict.fromkeys(m.group(0).lower() for m in _SCOPE_TERMS.finditer(page.text)))
        sigs = extract_signals(page.text)
        by_others = tuple(dict.fromkeys(m.group(0) for m in _BY_OTHERS.finditer(page.text)))
        score = len(terms) * 2 + len(sigs) + len(by_others) * 2
        if "millwork" in terms:
            score += 4
        if page.sheet and page.sheet.startswith(("A7.", "A8.", "A11.")):
            score += 2
        if score:
            rows.append(
                ScopePage(
                    path.name,
                    page.page_number,
                    page.sheet,
                    score,
                    terms,
                    tuple(asdict(s) for s in sigs),
                    by_others,
                )
            )
    return tuple(sorted(rows, key=lambda r: (-r.relevance_score, r.page)))
