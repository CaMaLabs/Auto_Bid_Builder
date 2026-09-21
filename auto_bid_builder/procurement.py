from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PurchaseEvidence:
    source: str
    vendor: str | None = None
    date: str | None = None
    po: str | None = None
    document_number: str | None = None
    document_kind: str | None = None
    item: str | None = None
    description: str | None = None
    quantity: float | None = None
    uom: str | None = None
    unit_cost: float | None = None
    line_amount: float | None = None
    freight: float | None = None
    tax: float | None = None
    document_total: float | None = None
    priced: bool = False

    @property
    def document_key(self) -> tuple[str, str]:
        return self.source, self.document_number or ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PurchaseDocumentSummary:
    source: str
    vendor: str | None
    document_number: str | None
    document_kind: str | None
    po: str | None
    date: str | None
    row_count: int
    priced_row_count: int
    known_total: float | None
    line_subtotal: float
    freight: float
    tax: float
    reconciliation_delta: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProcurementSummary:
    row_count: int
    document_count: int
    priced_document_count: int
    unpriced_document_count: int
    known_purchase_total: float
    quote_total: float | None
    observed_purchase_to_quote_ratio: float | None
    vendor_totals: dict[str, float]
    documents: tuple[PurchaseDocumentSummary, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace("$", "").replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "priced"}


def load_procurement_csv(path: str | Path) -> tuple[PurchaseEvidence, ...]:
    """Load normalized historical purchasing evidence.

    The CSV is intentionally simple so scanned vendor documents can be transcribed or
    populated by a future OCR/vision adapter without coupling the cost model to one vendor's
    document layout. Private purchasing data should stay outside the public repository.
    """
    rows: list[PurchaseEvidence] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            source = (raw.get("source") or "").strip()
            if not source:
                continue
            line_amount = _number(raw.get("line_amount"))
            document_total = _number(raw.get("document_total"))
            unit_cost = _number(raw.get("unit_cost"))
            explicit_priced = _bool(raw.get("priced"))
            rows.append(
                PurchaseEvidence(
                    source=source,
                    vendor=(raw.get("vendor") or "").strip() or None,
                    date=(raw.get("date") or "").strip() or None,
                    po=(raw.get("po") or "").strip() or None,
                    document_number=(raw.get("document_number") or "").strip() or None,
                    document_kind=(raw.get("document_kind") or "").strip() or None,
                    item=(raw.get("item") or "").strip() or None,
                    description=(raw.get("description") or "").strip() or None,
                    quantity=_number(raw.get("quantity")),
                    uom=(raw.get("uom") or "").strip() or None,
                    unit_cost=unit_cost,
                    line_amount=line_amount,
                    freight=_number(raw.get("freight")),
                    tax=_number(raw.get("tax")),
                    document_total=document_total,
                    priced=explicit_priced or any(x is not None for x in (unit_cost, line_amount, document_total)),
                )
            )
    return tuple(rows)


def _first(rows: list[PurchaseEvidence], attr: str):
    for row in rows:
        value = getattr(row, attr)
        if value not in (None, ""):
            return value
    return None


def summarize_procurement(rows: Iterable[PurchaseEvidence], *, quote_total: float | None = None) -> ProcurementSummary:
    rows = tuple(rows)
    grouped: dict[tuple[str, str], list[PurchaseEvidence]] = defaultdict(list)
    for row in rows:
        grouped[row.document_key].append(row)

    documents: list[PurchaseDocumentSummary] = []
    vendor_totals: dict[str, float] = defaultdict(float)
    known_purchase_total = 0.0

    for group in grouped.values():
        line_subtotal = round(sum(row.line_amount or 0.0 for row in group), 2)
        # Freight/tax/document total are document-level values. Use the first known value so
        # a normalized CSV may repeat them on each line without double-counting.
        freight = float(_first(group, "freight") or 0.0)
        tax = float(_first(group, "tax") or 0.0)
        displayed_total = _first(group, "document_total")
        if displayed_total is not None:
            known_total = round(float(displayed_total), 2)
        elif line_subtotal or freight or tax:
            known_total = round(line_subtotal + freight + tax, 2)
        else:
            known_total = None

        reconciliation_delta: float | None = None
        if displayed_total is not None and line_subtotal:
            reconciliation_delta = round(float(displayed_total) - (line_subtotal + freight + tax), 2)

        vendor = _first(group, "vendor")
        if known_total is not None:
            known_purchase_total += known_total
            vendor_totals[vendor or "Unknown vendor"] += known_total

        documents.append(
            PurchaseDocumentSummary(
                source=group[0].source,
                vendor=vendor,
                document_number=_first(group, "document_number"),
                document_kind=_first(group, "document_kind"),
                po=_first(group, "po"),
                date=_first(group, "date"),
                row_count=len(group),
                priced_row_count=sum(1 for row in group if row.priced),
                known_total=known_total,
                line_subtotal=line_subtotal,
                freight=round(freight, 2),
                tax=round(tax, 2),
                reconciliation_delta=reconciliation_delta,
            )
        )

    documents.sort(key=lambda d: (d.date or "", d.vendor or "", d.source))
    known_purchase_total = round(known_purchase_total, 2)
    ratio = None
    if quote_total not in (None, 0):
        ratio = known_purchase_total / float(quote_total)

    priced_documents = sum(1 for doc in documents if doc.known_total is not None)
    return ProcurementSummary(
        row_count=len(rows),
        document_count=len(documents),
        priced_document_count=priced_documents,
        unpriced_document_count=len(documents) - priced_documents,
        known_purchase_total=known_purchase_total,
        quote_total=quote_total,
        observed_purchase_to_quote_ratio=ratio,
        vendor_totals={k: round(v, 2) for k, v in sorted(vendor_totals.items())},
        documents=tuple(documents),
    )


def procurement_markdown(summary: ProcurementSummary) -> str:
    lines = [
        "# Historical Procurement Calibration",
        "",
        f"Documents represented: **{summary.document_count}**",
        f"Documents with recoverable cost: **{summary.priced_document_count}**",
        f"Documents without recoverable cost: **{summary.unpriced_document_count}**",
        f"Known purchase total: **${summary.known_purchase_total:,.2f}**",
    ]
    if summary.quote_total is not None:
        lines.append(f"Quoted sell total: **${summary.quote_total:,.2f}**")
        if summary.observed_purchase_to_quote_ratio is not None:
            lines.append(
                f"Observed documented purchases / quoted sell total: **{summary.observed_purchase_to_quote_ratio:.2%}**"
            )
    lines += [
        "",
        "> This ratio is evidence coverage, not gross margin. Unpriced delivery tickets, missing invoices, labor, outsourced fabrication, field installation, freight, tax, overhead, and other costs may be absent.",
        "",
        "## Vendor totals from priced documents",
        "",
    ]
    if summary.vendor_totals:
        for vendor, total in summary.vendor_totals.items():
            lines.append(f"- **{vendor}**: ${total:,.2f}")
    else:
        lines.append("No priced vendor documents were present.")

    lines += ["", "## Document reconciliation", ""]
    for doc in summary.documents:
        total = "unpriced" if doc.known_total is None else f"${doc.known_total:,.2f}"
        extra = ""
        if doc.reconciliation_delta not in (None, 0.0):
            extra = f"; displayed-vs-components delta ${doc.reconciliation_delta:,.2f}"
        lines.append(
            f"- **{doc.source}** — {doc.vendor or 'unknown vendor'}; {doc.document_kind or 'document'}; total {total}{extra}"
        )
    lines += [
        "",
        "> Historical purchasing evidence must not be treated as a complete job-cost report unless coverage has been verified by an estimator/accounting source.",
        "",
    ]
    return "\n".join(lines)
