from __future__ import annotations

from dataclasses import dataclass
import re


_FINISH_CODE_RE = re.compile(r"\b(?:WD|PL|SS|ST|MTL|WC|GL|BR|P|F|ACT|GF)\d+[A-Za-z]?\b", re.I)
_RFI_RE = re.compile(r"\bRFI\s*#?\s*(\d+)\b", re.I)
_DIM_RE = re.compile(
    r"(?<!\w)(?:\d+\s*'\s*-?\s*)?(?:\d+(?:\s+\d+/\d+)?(?:\.\d+)?)\s*\"|"
    r"(?<![\w.])\d{2,5}(?:\.\d+)?\s*mm\b",
    re.I,
)

_PHRASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("vif", re.compile(r"\bV\.?I\.?F\.?\b|\bverify\s+in\s+field\b", re.I)),
    ("coordinate_with_equipment", re.compile(r"\bcoord(?:inate|\.)?\s+w/?\s*equip(?:ment)?\b", re.I)),
    ("filler_panel", re.compile(r"\bfiller\s+panel\b", re.I)),
    ("notch_cabinet", re.compile(r"\bnotch\b.{0,80}\bcabinet\b", re.I | re.S)),
    ("integrated_lighting", re.compile(r"\bintegrated\s+(?:led\s+)?(?:up)?lighting\b", re.I)),
    ("lighting_by_other", re.compile(r"\blighting\b.{0,100}\b(?:by\s+others|electrical\s+subcontractor)\b", re.I | re.S)),
    ("blocking", re.compile(r"\b(?:blocking|backing)\b", re.I)),
    ("shop_drawings", re.compile(r"\bshop\s+drawings?\b", re.I)),
    ("millwork", re.compile(r"\bmillwork\b", re.I)),
    ("wood_beam", re.compile(r"\bdecorative\s+wood\s+beams?\b", re.I)),
    ("floating_shelf", re.compile(r"\bfloating\s+(?:wood\s+)?shelves?\b", re.I)),
    ("by_others", re.compile(r"\bby\s+others\b", re.I)),
)


@dataclass(frozen=True)
class RevisionSignals:
    finish_codes: frozenset[str]
    rfi_refs: frozenset[str]
    dimensions: frozenset[str]
    phrases: frozenset[str]


@dataclass(frozen=True)
class RevisionImpact:
    added_finish_codes: tuple[str, ...]
    removed_finish_codes: tuple[str, ...]
    added_rfi_refs: tuple[str, ...]
    removed_rfi_refs: tuple[str, ...]
    added_dimensions: tuple[str, ...]
    removed_dimensions: tuple[str, ...]
    added_phrases: tuple[str, ...]
    removed_phrases: tuple[str, ...]

    @property
    def has_scope_relevant_change(self) -> bool:
        return any(
            (
                self.added_finish_codes,
                self.removed_finish_codes,
                self.added_rfi_refs,
                self.removed_rfi_refs,
                self.added_dimensions,
                self.removed_dimensions,
                self.added_phrases,
                self.removed_phrases,
            )
        )


def _norm_dimension(value: str) -> str:
    return " ".join(value.replace("\u201d", '"').replace("\u2033", '"').split())


def extract_revision_signals(text: str) -> RevisionSignals:
    """Extract revision-stable signals from noisy PDF text.

    Architectural PDF text order changes easily between issues. Rather than line-diffing the
    entire extraction, this captures tokens that are usually meaningful to an estimator:
    finish codes, RFI references, dimensions, and scope/risk phrases.
    """
    finish_codes = frozenset(m.group(0).upper() for m in _FINISH_CODE_RE.finditer(text))
    rfi_refs = frozenset(m.group(1) for m in _RFI_RE.finditer(text))
    dimensions = frozenset(_norm_dimension(m.group(0)) for m in _DIM_RE.finditer(text))
    phrases = frozenset(name for name, pattern in _PHRASE_PATTERNS if pattern.search(text))
    return RevisionSignals(finish_codes, rfi_refs, dimensions, phrases)


def diff_revision_signals(old_text: str, new_text: str) -> RevisionImpact:
    old = extract_revision_signals(old_text)
    new = extract_revision_signals(new_text)

    def added(a: frozenset[str], b: frozenset[str]) -> tuple[str, ...]:
        return tuple(sorted(b - a))

    def removed(a: frozenset[str], b: frozenset[str]) -> tuple[str, ...]:
        return tuple(sorted(a - b))

    return RevisionImpact(
        added_finish_codes=added(old.finish_codes, new.finish_codes),
        removed_finish_codes=removed(old.finish_codes, new.finish_codes),
        added_rfi_refs=added(old.rfi_refs, new.rfi_refs),
        removed_rfi_refs=removed(old.rfi_refs, new.rfi_refs),
        added_dimensions=added(old.dimensions, new.dimensions),
        removed_dimensions=removed(old.dimensions, new.dimensions),
        added_phrases=added(old.phrases, new.phrases),
        removed_phrases=removed(old.phrases, new.phrases),
    )
