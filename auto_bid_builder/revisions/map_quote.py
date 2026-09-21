from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from auto_bid_builder.ingest.pdf import PdfPage
from auto_bid_builder.quote.jti import QuoteDocument
from auto_bid_builder.revisions.impact import RevisionImpact, diff_revision_signals


@dataclass(frozen=True)
class SheetImpact:
    sheet: str
    baseline_page: int | None
    revision_page: int
    impact: RevisionImpact


@dataclass(frozen=True)
class QuoteLineImpact:
    item: int
    description: str
    affected_sheets: tuple[str, ...]
    classification: str
    reasons: tuple[str, ...]


def _summarize(sheet: str, impact: RevisionImpact) -> tuple[str, ...]:
    reasons: list[str] = []
    if impact.added_rfi_refs:
        reasons.append(f"{sheet}: added RFI refs {', '.join(impact.added_rfi_refs)}")
    if impact.added_finish_codes or impact.removed_finish_codes:
        changes = []
        if impact.added_finish_codes:
            changes.append("+" + ",".join(impact.added_finish_codes))
        if impact.removed_finish_codes:
            changes.append("-" + ",".join(impact.removed_finish_codes))
        reasons.append(f"{sheet}: finish-code change {' '.join(changes)}")
    if impact.added_phrases or impact.removed_phrases:
        changes = []
        if impact.added_phrases:
            changes.append("+" + ",".join(impact.added_phrases))
        if impact.removed_phrases:
            changes.append("-" + ",".join(impact.removed_phrases))
        reasons.append(f"{sheet}: scope/risk signals {' '.join(changes)}")
    if impact.added_dimensions or impact.removed_dimensions:
        reasons.append(
            f"{sheet}: drawing dimensions changed "
            f"({len(impact.added_dimensions)} added / {len(impact.removed_dimensions)} removed)"
        )
    return tuple(reasons)


def _classify(impact: RevisionImpact) -> str:
    pricing_phrases = {"notch_cabinet", "filler_panel", "millwork", "wood_beam", "floating_shelf", "by_others"}
    if impact.added_finish_codes or impact.removed_finish_codes or impact.added_rfi_refs:
        return "pricing_review"
    if pricing_phrases.intersection(impact.added_phrases) or pricing_phrases.intersection(impact.removed_phrases):
        return "pricing_review"
    if impact.added_dimensions or impact.removed_dimensions or impact.added_phrases or impact.removed_phrases:
        return "coordination_review"
    return "no_material_signal_change"


def build_sheet_impacts(
    baseline_by_sheet: dict[str, PdfPage], revision_by_sheet: dict[str, PdfPage]
) -> dict[str, SheetImpact]:
    out: dict[str, SheetImpact] = {}
    for sheet, revised in revision_by_sheet.items():
        base = baseline_by_sheet.get(sheet)
        if not base:
            continue
        impact = diff_revision_signals(base.text, revised.text)
        if impact.has_scope_relevant_change:
            out[sheet] = SheetImpact(sheet, base.page_number, revised.page_number, impact)
    return out


def map_impacts_to_quote(
    quote: QuoteDocument, sheet_impacts: dict[str, SheetImpact]
) -> tuple[QuoteLineImpact, ...]:
    rows: list[QuoteLineImpact] = []
    for line in quote.lines:
        impacted = tuple(s for s in line.sheet_refs if s in sheet_impacts)
        if not impacted:
            continue
        classifications = [_classify(sheet_impacts[s].impact) for s in impacted]
        classification = "pricing_review" if "pricing_review" in classifications else "coordination_review"
        reasons: list[str] = []
        for sheet in impacted:
            reasons.extend(_summarize(sheet, sheet_impacts[sheet].impact))
        rows.append(
            QuoteLineImpact(
                item=line.item,
                description=line.description,
                affected_sheets=impacted,
                classification=classification,
                reasons=tuple(reasons),
            )
        )
    return tuple(rows)


def sheet_impacts_to_dict(items: dict[str, SheetImpact]) -> dict[str, Any]:
    return {sheet: asdict(value) for sheet, value in items.items()}
