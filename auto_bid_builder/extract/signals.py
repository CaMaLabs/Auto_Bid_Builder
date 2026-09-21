from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Signal:
    kind: str
    value: str
    confidence: float
    matched_text: str


_PATTERNS: tuple[tuple[str, re.Pattern[str], str, float], ...] = (
    (
        "responsibility",
        re.compile(r"\bprovided\s+by\s+(?:the\s+)?millwork(?:er)?\b", re.I),
        "millworker_provided",
        0.99,
    ),
    (
        "responsibility",
        re.compile(r"\bfurnished\s+by\s+(?:the\s+)?millwork(?:er)?\b", re.I),
        "millworker_furnished",
        0.99,
    ),
    ("custom", re.compile(r"\b(custom|modified)\b", re.I), "custom_or_modified", 0.95),
    ("verification", re.compile(r"\b(VIF|verify\s+in\s+field|field\s+verify)\b", re.I), "field_verification", 0.95),
    (
        "document_status",
        re.compile(r"shall\s+not\s+be\s+used\s+for\s+construction", re.I),
        "concept_not_for_construction",
        0.99,
    ),
    (
        "verification",
        re.compile(r"dimensions?.{0,80}(?:must|shall)\s+be\s+verified", re.I | re.S),
        "dimension_verification_required",
        0.96,
    ),
)

_MATERIAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bribbed\s+mdf\b", re.I), "ribbed MDF"),
    (re.compile(r"\bpainted\s+mdf\b", re.I), "painted MDF"),
    (re.compile(r"\b(?:powder\s+coated\s+(?:black\s+)?metal|(?:black\s+)?metal\s+powder\s+coated)\b", re.I), "powder-coated metal"),
    (re.compile(r"\bceramic\b", re.I), "ceramic"),
    (re.compile(r"\b(?:wool|tufted\s+wool)\s+carpet\b", re.I), "wool carpet"),
    (re.compile(r"\bglass\b", re.I), "glass"),
    (re.compile(r"\bneoprene\b", re.I), "neoprene"),
)

_MM_RE = re.compile(r"(?<![\w.])(\d{2,5}(?:\.\d+)?)\s*mm\b", re.I)
_FT_IN_RE = re.compile(r"(?<!\w)(\d+)\s*'\s*-?\s*(\d+(?:\s+\d+/\d+)?(?:\.\d+)?)?\s*\"?")


def extract_signals(text: str) -> list[Signal]:
    """Extract conservative, evidence-oriented bid signals from page/sheet text."""
    signals: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    for kind, pattern, value, confidence in _PATTERNS:
        for match in pattern.finditer(text):
            matched = " ".join(match.group(0).split())
            key = (kind, value, matched.lower())
            if key not in seen:
                signals.append(Signal(kind, value, confidence, matched))
                seen.add(key)

    for pattern, value in _MATERIAL_PATTERNS:
        for match in pattern.finditer(text):
            matched = " ".join(match.group(0).split())
            key = ("material", value, matched.lower())
            if key not in seen:
                signals.append(Signal("material", value, 0.92, matched))
                seen.add(key)

    for match in _MM_RE.finditer(text):
        matched = match.group(0)
        key = ("dimension_mm", match.group(1), matched)
        if key not in seen:
            signals.append(Signal("dimension_mm", match.group(1), 0.98, matched))
            seen.add(key)

    for match in _FT_IN_RE.finditer(text):
        matched = " ".join(match.group(0).split())
        value = matched
        key = ("dimension_imperial", value, matched)
        if key not in seen:
            signals.append(Signal("dimension_imperial", value, 0.96, matched))
            seen.add(key)

    return signals


def has_scope_trigger(signals: list[Signal]) -> bool:
    return any(s.kind == "responsibility" and s.value.startswith("millworker_") for s in signals)
