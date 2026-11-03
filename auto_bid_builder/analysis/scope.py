from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from auto_bid_builder.extract.signals import extract_signals
from auto_bid_builder.ingest.pdf import extract_pdf_pages


SCOPE_ANALYSIS_VERSION = 5


# High-precision fabrication/scope anchors. Generic words such as "panel" and
# "counter" are handled separately because they create many false positives in
# electrical, accessibility, playground, and structural documents.
_STRONG_SCOPE_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("millwork", re.compile(r"\b(?:architectural\s+)?millwork\b", re.I)),
    ("casework", re.compile(r"\bcasework\b", re.I)),
    ("cabinetry", re.compile(r"\bcabinetry\b", re.I)),
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
        "cabinetry",
        re.compile(r"\bcabinets?\b", re.I),
        re.compile(
            r"\b(?:architectural|wood|plywood|veneer|laminate|plam|millwork|casework|"
            r"kitchen|reception|solid\s+surface|countertop)\b",
            re.I,
        ),
    ),
    (
        "counter",
        re.compile(r"\bcounter(?:s)?\b", re.I),
        re.compile(r"\b(?:solid\s+surface|plastic\s+laminate|plam|stone|wood|veneer|millwork|casework|transaction|service|reception)\b", re.I),
    ),
    (
        "panel",
        re.compile(r"\bpanel(?:s)?\b", re.I),
        re.compile(r"\b(?:wood|veneer|mdf|millwork|casework|decorative|laminate|plam|ribbed|slat(?:ted)?)\b", re.I),
    ),
)

_FALSE_POSITIVE_PHRASES = re.compile(
    r"\b(?:over[- ]the[- ]counter|counter[- ]slop(?:e|ing)|panelboards?|electrical\s+panels?|"
    r"playground\s+(?:gear\s+)?panels?|metal\s+panels?|control(?:\s+and\s+monitoring)?\s+panels?|"
    r"monitoring\s+panels?|pump\s+control\s+panels?|access\s+panels?|communications\s+cabinets?|"
    r"terminal\s+cabinets?|sheet\s+metal\s+cabinets?|electrical\s+cabinets?|spare[- ]fuse\s+cabinets?|"
    r"switchboards?|motor[- ]control\s+centers?|distribution\s+panels?)\b",
    re.I,
)

_NON_MILLWORK_EQUIPMENT_CONTEXT = re.compile(
    r"\b(?:NFPA\s*70|NEMA\s*(?:1|3R|4X|12|250)|UL\s*(?:50|50E|508A)|"
    r"electrical|communications?|conduit|raceway|switchboard|panelboard|generator|"
    r"battery\s+charger|terminal\s+strip|circuit\s+breaker|VFD|PLC|SCADA|"
    r"enclosure|wiring|conductor|transformer)\b",
    re.I,
)

# A word such as "cabinet", "panel" or "shelves" is not a millwork scope
# statement when it belongs to a different CSI trade. These are strong
# disqualifiers for automatic pricing; the supporting PDFs remain available
# to the estimator for manual review.
_OTHER_TRADE_SECTION = re.compile(
    r"\b(?:SECTION\s+)?(?:20|21|22|23|25|26|27|28|31|32|33)\s?\d{2}\s?\d{2}\b",
    re.I,
)
_OTHER_TRADE_TITLE = re.compile(
    r"(?im)^\s*(?:ACCESS CONTROL|VIDEO SURVEILLANCE|COMMUNICATIONS (?:EQUIPMENT|HORIZONTAL|OPTICAL)|"
    r"DOOR HARDWARE|ELECTRICAL (?:CABINETS|POWER|SYSTEMS)|"
    r"PLUMBING (?:FIXTURES|SPECIALTIES)|FIRE ALARM(?: SYSTEMS)?)\s*$"
)
_EQUIPMENT_ACCESSORIES = re.compile(
    r"\b(?:key\s+control|hardware\s+supplier|card\s+readers?|terminal\s+strips?|"
    r"security\s+system|access\s+control|storage\s+(?:cabinet|rack)|"
    r"equipment\s+(?:rack|enclosure|cabinet)|disks?|tapes?|printer\s+paper|"
    r"locking\s+cabinet|wiring\s+closet|telecommunications|steel\s+or\s+aluminum|"
    r"louvered\s+side\s+panels?|cabling|fiber\s+optic)\b",
    re.I,
)
_REFERENCE_ONLY = re.compile(
    r"\b(?:within\s+(?:cabinets?\s+and\s+)?millwork|"
    r"(?:fixtures|accessories|equipment),?\s+casework\s+etc\.?|"
    r"for\s+(?:typical\s+)?backing\s*/?\s*blocking|"
    r"coordination\s+(?:with|of)\s+(?:the\s+)?millwork)\b",
    re.I,
)
_CHECKLIST_LANGUAGE = re.compile(
    r"(?is)\b(?:CHANGE ROOM\s+YES\s+NO|Hangers/lockers/bins\s+for\s+street\s+clothes\?|"
    r"APPENDIX\s+['\"]?C['\"]?\s+Section\s+01\s+45)\b"
)
_FABRICATION_VERBS = re.compile(
    r"\b(?:provide|furnish|fabricate|construct|install|build|manufacture|supply)\b",
    re.I,
)
_ARCHITECTURAL_MATERIAL = re.compile(
    r"\b(?:architectural\s+millwork|casework|wood\s+veneer|plywood|"
    r"plastic\s+laminate|high-pressure\s+laminate|solid\s+surface|"
    r"melamine|mdf|hardwood|cabinetry)\b",
    re.I,
)
_GLOSSARY_PAGE = re.compile(
    r"\b(?:ARCHITECTURAL\s+ABBREVIATIONS|SYMBOL\s+LEGEND|"
    r"MATERIAL\s+LEGEND|DRAWING\s+ABBREVIATIONS)\b",
    re.I,
)


def _non_priceable_page_context(text: str) -> bool:
    # Appendix inspection checklists and other-trade specifications must not
    # generate JTI prices from generic nouns. Match sections near the page's
    # start/end; a reference to another spec section in the middle is not enough.
    if _CHECKLIST_LANGUAGE.search(text):
        return True
    head_tail = text[:450] + "\n" + text[-350:]
    if _OTHER_TRADE_SECTION.search(head_tail) or _OTHER_TRADE_TITLE.search(head_tail):
        return True
    if _GLOSSARY_PAGE.search(text) and not re.search(
        r"\b(?:FURNISH|FABRICATE|INSTALL|PROVIDE)\b.{0,120}\b(?:MILLWORK|CASEWORK|CABINETRY)\b",
        text,
        re.I | re.S,
    ):
        return True
    return False


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

    if _non_priceable_page_context(text):
        return (), ()

    for label, pattern in _STRONG_SCOPE_TERMS:
        for match in pattern.finditer(text):
            nearby = _context(text, match.start(), match.end())
            if _FALSE_POSITIVE_PHRASES.search(nearby) or _REFERENCE_ONLY.search(nearby):
                continue
            if label in {"shelving", "locker"} and not (
                _ARCHITECTURAL_MATERIAL.search(nearby)
                or (_FABRICATION_VERBS.search(nearby) and not _EQUIPMENT_ACCESSORIES.search(nearby))
            ):
                continue
            if _EQUIPMENT_ACCESSORIES.search(nearby):
                continue
            target = demolition if _DEMOLITION.search(nearby) else positive
            if label not in target:
                target.append(label)

    for label, pattern, required_context in _CONTEXTUAL_SCOPE_TERMS:
        for match in pattern.finditer(text):
            nearby = _context(text, match.start(), match.end())
            if _FALSE_POSITIVE_PHRASES.search(nearby):
                continue
            if _NON_MILLWORK_EQUIPMENT_CONTEXT.search(nearby) or _EQUIPMENT_ACCESSORIES.search(nearby):
                continue
            # Generic cabinet/counter/panel references must have nearby
            # architectural fabrication/material context. This intentionally
            # prefers precision over recall.
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
