from __future__ import annotations

from auto_bid_builder.quote.jti import QuoteDocument
from auto_bid_builder.revisions.map_quote import QuoteLineImpact, SheetImpact


def revision_report_markdown(
    quote: QuoteDocument,
    sheet_impacts: dict[str, SheetImpact],
    line_impacts: tuple[QuoteLineImpact, ...],
) -> str:
    h = quote.header
    out = [
        "# Auto Bid Builder - Revision Audit",
        "",
        f"Quote: {h.number or 'unknown'} - {h.description or 'unknown'}",
        f"Quoted total: ${quote.quote_total:,.2f}" if quote.quote_total is not None else "Quoted total: unknown",
        "",
        "## Summary",
        "",
        f"- Quote lines parsed: {len(quote.lines)}",
        f"- Revised baseline-matched sheets with estimator signals: {len(sheet_impacts)}",
        f"- Quote lines requiring review: {len(line_impacts)}",
        "",
    ]
    if line_impacts:
        out += ["## Quote line review queue", ""]
        for row in line_impacts:
            out.append(f"### Item {row.item} - {row.classification.replace('_', ' ').title()}")
            out.append(row.description)
            out.append("")
            for reason in row.reasons:
                out.append(f"- {reason}")
            out.append("")
    out += [
        "## Unmapped quote lines",
        "",
        "These lines have no explicit drawing-sheet reference in the quote description, so V1 does not guess at a revision mapping:",
        "",
    ]
    for line in quote.lines:
        if not line.sheet_refs:
            out.append(f"- Item {line.item}: {line.description}")
    out += [
        "",
        "## V1 interpretation",
        "",
        "A review flag means the referenced sheet changed in estimator-relevant ways. It does not by itself prove that JTI owes added work or is entitled to a change order; estimator review is required.",
        "",
    ]
    return "\n".join(out)
