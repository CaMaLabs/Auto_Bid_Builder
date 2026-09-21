from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

import pdfplumber

from auto_bid_builder.estimate.cost_detail import CostDetailDocument


_MONEY = r"\$?\s*([0-9][0-9,]*\.\d{2})"


@dataclass(frozen=True)
class ChangeOrderDocument:
    subcontract_number: str | None
    change_order_number: int | None
    project_name: str | None
    description: str | None
    original_contract_value: float | None
    previous_change_orders: float | None
    change_order_amount: float | None
    adjusted_contract_value: float | None

    @property
    def change_order_ref(self) -> str | None:
        return f"CO{self.change_order_number}" if self.change_order_number is not None else None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["change_order_ref"] = self.change_order_ref
        return data


def _money(text: str | None) -> float | None:
    if text is None:
        return None
    return float(text.replace(",", "").replace("$", "").strip())


def _first(pattern: str, text: str, flags: int = re.I | re.M) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def parse_change_order_text(text: str) -> ChangeOrderDocument:
    subcontract_number = _first(r"Subcontract\s*#:\s*([^\n\r]+)", text)
    change_order_text = _first(r"(?:SCO\s+No\.|Change\s+Order\s+No[:.]?)\s*#?\s*(\d+)", text)
    if change_order_text is None:
        change_order_text = _first(r"Subcontract\s+Change\s+Order\s+No:\s*#?\s*(\d+)", text)

    project_name = _first(r"PROJECT:\s*([^\n\r]+)", text)
    if project_name is None:
        project_name = _first(r"^([^\n\r]+)\s*$", text)

    description = None
    compact = " ".join(text.split())
    pco = re.search(
        rf"SPG\s+PCO\s*#\s+Description\s+Amount\s+\d+\s+(.+?)\s+(?:Proposal\s+dated\s+)?{_MONEY}",
        compact,
        re.I,
    )
    if pco:
        description = " ".join(pco.group(1).split())

    original = _first(rf"Original\s+Subcontract\s+Value:\s*{_MONEY}", text)
    previous = _first(rf"Net\s+Change\s+by\s+Previous\s+Change\s+Orders:\s*{_MONEY}", text)
    amount = _first(rf"Amount\s+of\s+This\s+Change\s+Order(?:\s*\(No\.\s*\d+\))?:\s*{_MONEY}", text)
    adjusted = _first(rf"Current\s+Adjusted\s+Subcontract\s+Value:\s*{_MONEY}", text)

    return ChangeOrderDocument(
        subcontract_number=subcontract_number,
        change_order_number=int(change_order_text) if change_order_text is not None else None,
        project_name=project_name,
        description=description,
        original_contract_value=_money(original),
        previous_change_orders=_money(previous),
        change_order_amount=_money(amount),
        adjusted_contract_value=_money(adjusted),
    )


def parse_change_order_pdf(path: str | Path) -> ChangeOrderDocument:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
    return parse_change_order_text("\n".join(chunks))


def reconcile_cost_detail_to_change_order(
    cost_detail: CostDetailDocument,
    change_order: ChangeOrderDocument,
    *,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    change_order_refs = sorted(
        {line.change_order_ref for line in cost_detail.lines if line.change_order_ref is not None}
    )
    ref_matches = None
    if change_order.change_order_ref is not None:
        ref_matches = change_order.change_order_ref in change_order_refs

    base_matches = _matches(
        cost_detail.inferred_base_contract_total,
        change_order.original_contract_value,
        tolerance,
    )
    change_matches = _matches(
        cost_detail.change_order_total,
        change_order.change_order_amount,
        tolerance,
    )
    job_total = cost_detail.displayed_totals.job_total
    if job_total is None:
        job_total = cost_detail.calculated_totals.job_total
    adjusted_matches = _matches(job_total, change_order.adjusted_contract_value, tolerance)

    checks = [x for x in (ref_matches, base_matches, change_matches, adjusted_matches) if x is not None]
    return {
        "cost_detail_job_number": cost_detail.job_number,
        "change_order_ref": change_order.change_order_ref,
        "cost_detail_change_order_refs": change_order_refs,
        "cost_detail_inferred_base_contract_total": cost_detail.inferred_base_contract_total,
        "change_order_original_contract_value": change_order.original_contract_value,
        "cost_detail_change_order_total": cost_detail.change_order_total,
        "change_order_amount": change_order.change_order_amount,
        "cost_detail_job_total": job_total,
        "change_order_adjusted_contract_value": change_order.adjusted_contract_value,
        "change_order_ref_matches": ref_matches,
        "base_contract_value_matches": base_matches,
        "change_order_amount_matches": change_matches,
        "adjusted_contract_value_matches": adjusted_matches,
        "all_available_checks_match": all(checks) if checks else None,
    }


def _matches(a: float | None, b: float | None, tolerance: float) -> bool | None:
    if a is None or b is None:
        return None
    return abs(a - b) <= tolerance
