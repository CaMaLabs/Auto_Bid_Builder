from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from auto_bid_builder.extract.signals import extract_signals
from auto_bid_builder.ingest.pdf import extract_pdf_pages


# High-precision fabrication/scope anchors. Generic words such as "panel" and
# "counter" are handled separately because they create many false positives in
# electrical, accessibility, playground, and structural documents.
_STRONG_SCOPE_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("millwork", re.compile(r"\b(?:architectural\s+)?millwork\b", re.I)),
    ("casework", re.compile(r"\bcasework\b", re.I)),
    ("cabinetry", re.compile(r"\bcabinet(?:ry|s)?\b", re.I)),
    ("shelving", re.compile(r"\bshelv(?:e|es|ing)\b|\bfloating\s+shel(?:f|ves)\b", re.I)),
    ("reception desk", re.compile(r"\breception\s+desk\b", re.I)),
    ("countertop", re.compile(r"\bcountertop(?:s)?\b|\bworktop(?:s)?\b", re.I)),
    ("wood veneer", re.compile(r"\bwood\s+veneer\b|\bveneer(?:ed)?\s+(?:wood|panel|casework|cabinet)\b", re.I)),
    ("wood cladding", re.compile(r"\bwood\s+cladding\b", re.I)),
    ("locker", re.compile(r"\blocker(?:s)?\b", re.I)),
    ("wood beam", re.compile(r"\bwood\s+beam(?:s)?\b", re.I)),
    ("banquette", re.compile(r"\bbanquette(?:s)?\b", re.I)),
    ("cashwrap", re.compile(r"\bcash\s*wrap(?:s)?\b|\bback\s*wrap(?:s)?\b", re.I)),
)

# Generic terms are accepted only with fabrication/material context.
_CONTEXTUAL_SCOPE_TERMS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    (
        "counter",
        re.compile(r"\bcounter(?:s)?\b", re.I),
        re.compile(r"\b(?:solid\s+surface|plastic\s+laminate|plam|stone|wood|veneer|millwork|casework|cabinet|transaction|service|reception)\b", re.I),
    ),
    (
        "panel",
        re.compile(r"\bpanel(?:s)?\b", re.I),
        re.compile(r"\b(?:wood|veneer|mdf|millwork|casework|cabinet|decorative|laminate|plam|ribbed|slat(?:ted)?)\b", re.I),
    ),
)

_FALSE_POSITIVE_PHRASES = re.compile(
    r"\b(?:over[- ]the[- ]counter|counter[- ]slop(?:e|ing)|panelboard|electrical\s+panel|"
    r"playground\s+(?:gear\s+)?panel|metal\s+panel|control\s+panel|access\s+panel)\b",
    re.I,
)
_DEMOLITION = re.compile(r"\b(?:remove|demolish|demo|existing\s+to\s+be\s+removed|salvage)\b", re.I)
_BY_OTHERS = re.compile(r"\b(by others|not included|electrical subcontractor|GCs?\s+electrical)\b", re.I)
_ADJACENT_REVIEW = (
    ("rough carpentry", re.compile(r"\brough\s+carpentry\b", re.I)),
    ("blocking", re.compile(r"\b(?:wood\s+)?blocking\b|\bnailers?\b", re.I)),
    ("flush wood doors", re.compile(r"\bflush\s+wood\s+doors?\b", re.I)),
)


@dataclass(frozen=True)
class ScopePage:
    source: str
    page: int
    sheet: str | None
    relevance_score: int
    scope_terms: tuple[str, ...]
    signals: tuple[dict[str, Any], ...]
    by_others_mentions: tuple[str, ...]
    demolition_terms: tuple[str, ...] = ()
    adjacent_review_terms: tuple[str, ...] = ()


def _context(text: str, start: int, end: int, radius: int = 100) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


def _positive_scope_terms(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    positive: list[str] = []
    demolition: list[str] = []

    for label, pattern in _STRONG_SCOPE_TERMS:
        for match in pattern.finditer(text):
            nearby = _context(text, match.start(), match.end())
            if _FALSE_POSITIVE_PHRASES.search(nearby):
                continue
            target = demolition if _DEMOLITION.search(nearby) else positive
            if label not in target:
                target.append(label)

    for label, pattern, required_context in _CONTEXTUAL_SCOPE_TERMS:
        for match in pattern.finditer(text):
            nearby = _context(text, match.start(), match.end())
            if _FALSE_POSITIVE_PHRASES.search(nearby):
                continue
            # Generic counter/panel references must have nearby fabrication/material
            # context. This intentionally prefers precision over recall.
            if not required_context.search(nearby):
                continue
            target = demolition if _DEMOLITION.search(nearby) else positive
            if label not in target:
                target.append(label)

    return tuple(positive), tuple(demolition)


def _adjacent_review_terms(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for label, pattern in _ADJACENT_REVIEW:
        if pattern.search(text) and label not in found:
            found.append(label)
    return tuple(found)


def _scan_text(*, source: str, page_number: int, text: str, sheet: str | None = None) -> ScopePage | None:
    terms, demolition_terms = _positive_scope_terms(text)
    adjacent = _adjacent_review_terms(text)
    sigs = extract_signals(text)
    by_others = tuple(dict.fromkeys(m.group(0) for m in _BY_OTHERS.finditer(text)))

    responsibility = [
        sig for sig in sigs
        if sig.kind == "responsibility" and str(sig.value).startswith("millworker_")
    ]

    # Dimensions/materials/by-others language alone no longer makes a page a
    # millwork scope candidate. It must contain actual scope language or an explicit
    # millworker responsibility statement. Demolition and adjacent-trade evidence is
    # retained for review but is not auto-priced as new fabrication.
    if not terms and not responsibility and not demolition_terms and not adjacent:
        return None

    score = len(terms) * 4 + len(responsibility) * 6
    score += len(demolition_terms) * 2 + len(adjacent)
    if "millwork" in terms:
        score += 4
    if sheet and sheet.startswith(("A7.", "A8.", "A11.")) and (terms or responsibility):
        score += 2

    return ScopePage(
        source=source,
        page=page_number,
        sheet=sheet,
        relevance_score=score,
        scope_terms=terms,
        signals=tuple(asdict(s) for s in sigs),
        by_others_mentions=by_others,
        demolition_terms=demolition_terms,
        adjacent_review_terms=adjacent,
    )


def scan_text(text: str, *, source: str, page_number: int = 1, sheet: str | None = None) -> ScopePage | None:
    """Scan non-PDF text (for example DOCX addenda) with the same scope rules."""
    return _scan_text(source=source, page_number=page_number, text=text, sheet=sheet)


def scan_pdf(path: str | Path) -> tuple[ScopePage, ...]:
    path = Path(path)
    rows: list[ScopePage] = []
    for page in extract_pdf_pages(path):
        row = _scan_text(source=path.name, page_number=page.page_number, text=page.text, sheet=page.sheet)
        if row is not None:
            rows.append(row)
    return tuple(sorted(rows, key=lambda r: (-r.relevance_score, r.page)))
