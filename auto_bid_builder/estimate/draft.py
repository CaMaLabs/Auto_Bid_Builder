from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from html import escape
import json
from pathlib import Path
from typing import Any

import fitz


ESTIMATE_DRAFT_NAME = "estimate_draft.json"
QUOTE_PREVIEW_HTML = "quote_preview.html"
QUOTE_PREVIEW_PDF = "quote_preview.pdf"
LABOR_CATEGORIES = ("E", "M", "P", "A", "F", "H", "S", "I")

# Historical JTI cost-detail examples repeatedly used $100/hr for these shop-side
# categories. Installation varied materially by job, so I intentionally starts at
# zero. These are starter values only; the estimator must confirm pricing before a
# quote can be marked ready.
HISTORICAL_STARTER_LABOR_RATES: dict[str, float] = {
    "E": 100.0,
    "M": 100.0,
    "P": 100.0,
    "A": 100.0,
    "F": 100.0,
    "H": 100.0,
    "S": 100.0,
    "I": 0.0,
}
HISTORICAL_STARTER_MATERIAL_MARKUP = 0.60


@dataclass
class EstimateLine:
    item: int
    description: str
    quantity: float = 1.0
    labor_hours: dict[str, float] = field(default_factory=dict)
    material_cost: float = 0.0
    material_markup_rate: float = HISTORICAL_STARTER_MATERIAL_MARKUP
    manual_add: float = 0.0
    material_tax_rate: float = 0.0
    code: str = "MILL"
    source_refs: list[str] = field(default_factory=list)
    included: bool = True
    estimator_note: str = ""

    def normalized_hours(self) -> dict[str, float]:
        return {key: float(self.labor_hours.get(key, 0.0) or 0.0) for key in LABOR_CATEGORIES}

    def labor_total(self, labor_rates: dict[str, float]) -> float:
        hours = self.normalized_hours()
        return round(sum(hours[key] * float(labor_rates.get(key, 0.0) or 0.0) for key in LABOR_CATEGORIES), 2)

    @property
    def material_markup(self) -> float:
        return round(self.material_cost * self.material_markup_rate, 2)

    @property
    def material_tax(self) -> float:
        return round(self.material_cost * self.material_tax_rate, 2)

    def pretax_total(self, labor_rates: dict[str, float]) -> float:
        return round(self.labor_total(labor_rates) + self.material_cost + self.material_markup + self.manual_add, 2)

    def sell_total(self, labor_rates: dict[str, float]) -> float:
        if not self.included:
            return 0.0
        return round(self.pretax_total(labor_rates) + self.material_tax, 2)

    def quote_each(self, labor_rates: dict[str, float]) -> float:
        qty = self.quantity if self.quantity > 0 else 1.0
        return round(self.pretax_total(labor_rates) / qty, 2)

    @property
    def tax_each(self) -> float:
        qty = self.quantity if self.quantity > 0 else 1.0
        return round(self.material_tax / qty, 2)


@dataclass
class EstimateDraft:
    project_title: str
    quote_number: str = "DRAFT"
    quote_date: str = field(default_factory=lambda: date.today().isoformat())
    terms: str = ""
    rep: str = ""
    general_notes: str = ""
    labor_rates: dict[str, float] = field(default_factory=lambda: dict(HISTORICAL_STARTER_LABOR_RATES))
    pricing_profile_confirmed: bool = False
    tax_rate_confirmed: bool = False
    scope_review_confirmed: bool = False
    lines: list[EstimateLine] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(line.sell_total(self.labor_rates) for line in self.lines), 2)

    @property
    def included_line_count(self) -> int:
        return sum(1 for line in self.lines if line.included)

    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if not self.scope_review_confirmed:
            warnings.append("Scope review has not been confirmed by an estimator.")
        if not self.pricing_profile_confirmed:
            warnings.append("Labor rates / pricing profile have not been confirmed for this bid.")
        if any(line.material_cost > 0 for line in self.lines) and not self.tax_rate_confirmed:
            warnings.append("Material tax rate has not been confirmed for this bid.")
        if not self.lines:
            warnings.append("No estimate lines exist yet.")
        for line in self.lines:
            if not line.included:
                continue
            if line.quantity <= 0:
                warnings.append(f"Item {line.item}: quantity must be greater than zero.")
            if not line.description.strip():
                warnings.append(f"Item {line.item}: description is blank.")
            if sum(line.normalized_hours().values()) == 0 and line.material_cost == 0 and line.manual_add == 0:
                warnings.append(f"Item {line.item}: no labor, material, or add-on pricing has been entered.")
            if line.normalized_hours().get("I", 0.0) > 0 and float(self.labor_rates.get("I", 0.0) or 0.0) <= 0:
                warnings.append(f"Item {line.item}: installation hours exist but the I labor rate is zero.")
        return warnings

    @property
    def ready_for_quote(self) -> bool:
        return not self.warnings()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total"] = self.total
        data["warnings"] = self.warnings()
        data["ready_for_quote"] = self.ready_for_quote
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EstimateDraft":
        lines = [EstimateLine(**row) for row in data.get("lines", [])]
        labor_rates = dict(HISTORICAL_STARTER_LABOR_RATES)
        labor_rates.update({str(k): float(v or 0.0) for k, v in (data.get("labor_rates") or {}).items()})
        return cls(
            project_title=str(data.get("project_title") or "Untitled Bid"),
            quote_number=str(data.get("quote_number") or "DRAFT"),
            quote_date=str(data.get("quote_date") or date.today().isoformat()),
            terms=str(data.get("terms") or ""),
            rep=str(data.get("rep") or ""),
            general_notes=str(data.get("general_notes") or ""),
            labor_rates=labor_rates,
            pricing_profile_confirmed=bool(data.get("pricing_profile_confirmed", False)),
            tax_rate_confirmed=bool(data.get("tax_rate_confirmed", False)),
            scope_review_confirmed=bool(data.get("scope_review_confirmed", False)),
            lines=lines,
        )


def _estimate_path(root: str | Path) -> Path:
    root = Path(root)
    folder = root / "estimate"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ESTIMATE_DRAFT_NAME


def save_estimate(root: str | Path, draft: EstimateDraft) -> Path:
    path = _estimate_path(root)
    path.write_text(json.dumps(draft.to_dict(), indent=2), encoding="utf-8")
    return path


def load_estimate(root: str | Path) -> EstimateDraft | None:
    path = _estimate_path(root)
    if not path.exists():
        return None
    return EstimateDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))


_ITEMIZED_SCOPE_LABELS: dict[str, str] = {
    "millwork": "Architectural millwork",
    "casework": "Casework / cabinetry",
    "cabinetry": "Casework / cabinetry",
    "cabinet": "Casework / cabinetry",
    "shelving": "Shelving",
    "reception desk": "Reception desk",
    "countertop": "Countertops / worktops",
    "counter": "Counters",
    "wood veneer": "Wood veneer",
    "wood cladding": "Wood cladding",
    "locker": "Lockers",
    "wood beam": "Wood beams",
    "banquette": "Banquettes",
    "cashwrap": "Cashwrap / backwrap",
    "panel": "Decorative panels",
}


def _itemized_scope_label(term: str) -> str:
    cleaned = str(term or "").strip().lower()
    return _ITEMIZED_SCOPE_LABELS.get(cleaned, cleaned.replace("_", " ").title() or "Architectural millwork")


def _candidate_lines_from_review(root: Path) -> list[EstimateLine]:
    """Create evidence-backed estimate rows without collapsing unrelated scope.

    Rows are itemized by canonical scope type and drawing/spec reference. Synonyms
    such as casework/cabinetry on the same reference become one line, while the same
    scope on a different sheet/page remains separately reviewable. This intentionally
    favors estimator visibility over a small number of broad allowance buckets.
    """
    review = root / "output" / "bid_review.json"
    if not review.exists():
        return []
    try:
        payload = json.loads(review.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in payload.get("pages", []):
        sheet = str(row.get("sheet") or "").strip()
        source = str(row.get("source") or "Bid document")
        page = int(row.get("page") or 0)
        location = sheet or f"page {page}"
        ref = f"{source} / {sheet}" if sheet else f"{source} / page {page}"
        score = int(row.get("relevance_score", 0) or 0)

        labels: list[str] = []
        for raw_term in row.get("scope_terms") or []:
            label = _itemized_scope_label(str(raw_term))
            if label not in labels:
                labels.append(label)

        # A page can be relevant because it explicitly assigns responsibility to the
        # millworker even when it does not repeat a fabrication noun.
        if not labels:
            for signal in row.get("signals") or []:
                if (
                    str(signal.get("kind") or "") == "responsibility"
                    and str(signal.get("value") or "").startswith("millworker_")
                ):
                    labels.append("Architectural millwork responsibility")
                    break

        for label in labels:
            key = (source.lower(), location.lower(), label.lower())
            if key in seen:
                continue
            seen.add(key)
            description = f"{label} ({location})"
            candidates.append(
                {
                    "score": score,
                    "source": source,
                    "page": page,
                    "sheet": sheet,
                    "label": label,
                    "description": description,
                    "ref": ref,
                }
            )

    ordered = sorted(
        candidates,
        key=lambda item: (
            -int(item["score"]),
            item["source"].lower(),
            item["sheet"].lower() if item["sheet"] else f"{int(item['page']):06d}",
            item["label"].lower(),
        ),
    )
    lines: list[EstimateLine] = []
    for index, item in enumerate(ordered[:100], start=1):
        lines.append(
            EstimateLine(
                item=index,
                description=item["description"],
                source_refs=[item["ref"]],
                estimator_note=(
                    f"AUTO-SCOPE: {item['label']} detected from {item['ref']}. "
                    "Verify actual quantity, dimensions, finish, and responsibility."
                ),
            )
        )
    return lines


def rebuild_itemized_scope_from_workspace(root: str | Path, draft: EstimateDraft) -> int:
    """Replace generated scope rows from the latest document review and re-price them.

    Quote metadata and the current labor-rate profile are preserved. This is an
    explicit estimator action because it replaces the existing scope lines.
    """
    root = Path(root)
    draft.lines = _candidate_lines_from_review(root)
    from .autoprice import apply_auto_pricing

    if draft.lines:
        apply_auto_pricing(draft, overwrite=False, collapse_generated=False)
    draft.scope_review_confirmed = False
    draft.pricing_profile_confirmed = False
    draft.tax_rate_confirmed = False
    save_estimate(root, draft)
    return len(draft.lines)


def _line_is_auto_generated(line: EstimateLine) -> bool:
    note = str(line.estimator_note or "")
    return "AUTO-SCOPE:" in note


def _remove_stale_quote_outputs(root: Path) -> None:
    output = root / "output"
    for name in (
        "jti_quote.pdf",
        "jti_quote.html",
        "quote_preview.pdf",
        "quote_preview.html",
        "AI_review_package.zip",
    ):
        try:
            (output / name).unlink(missing_ok=True)
        except OSError:
            pass


def refresh_estimate_after_analysis(root: str | Path) -> dict[str, Any]:
    """Synchronize a saved estimate with a newly generated document review.

    Unreviewed machine-generated scope is rebuilt automatically from the new review,
    which prevents stale false-positive lines from surviving scanner improvements.
    Estimates that appear to contain estimator-reviewed/manual work are preserved but
    their review confirmations are cleared and stale quote outputs are removed.
    """
    root = Path(root)
    draft = load_estimate(root)
    _remove_stale_quote_outputs(root)
    if draft is None:
        return {"status": "no_estimate", "line_count": 0}

    auto_generated = bool(draft.lines) and all(_line_is_auto_generated(line) for line in draft.lines)
    estimator_confirmed = (
        draft.scope_review_confirmed
        or draft.pricing_profile_confirmed
        or draft.tax_rate_confirmed
    )

    if auto_generated and not estimator_confirmed:
        count = rebuild_itemized_scope_from_workspace(root, draft)
        return {
            "status": "rebuilt_auto_generated",
            "line_count": count,
        }

    # Preserve any manual/reviewed estimate, but never let a fresh document analysis
    # leave it appearing ready for quote.
    draft.scope_review_confirmed = False
    draft.pricing_profile_confirmed = False
    draft.tax_rate_confirmed = False
    marker = (
        "STALE-SCOPE: Bid documents were re-analyzed after this estimate was created. "
        "Review or rebuild itemized scope before generating a quote."
    )
    if marker not in draft.general_notes:
        draft.general_notes = (draft.general_notes + "\n" + marker).strip()
    save_estimate(root, draft)
    return {
        "status": "manual_estimate_preserved_stale",
        "line_count": len(draft.lines),
    }


def create_estimate_from_workspace(root: str | Path, project_title: str | None = None) -> EstimateDraft:
    root = Path(root)
    if project_title is None:
        manifest_path = root / "bid_workspace.json"
        title = root.name
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                opp = manifest.get("opportunity", {}).get("opportunity", manifest.get("opportunity", {}))
                title = str(opp.get("title") or title)
            except (OSError, json.JSONDecodeError):
                pass
        project_title = title
    draft = EstimateDraft(project_title=project_title, lines=_candidate_lines_from_review(root))
    if draft.lines:
        # Lazy import avoids a module cycle: autoprice uses EstimateDraft/EstimateLine,
        # while new drafts should arrive with useful provisional values instead of a
        # wall of zero-dollar rows.
        from .autoprice import apply_auto_pricing

        apply_auto_pricing(draft, overwrite=False, collapse_generated=False)
    save_estimate(root, draft)
    return draft


def quote_preview_html(draft: EstimateDraft) -> str:
    warnings = draft.warnings()
    rows: list[str] = []
    for line in draft.lines:
        if not line.included:
            continue
        rows.append(
            "<tr>"
            f"<td>{line.item}</td>"
            f"<td>{escape(line.description)}</td>"
            f"<td class='num'>{line.quantity:g}</td>"
            f"<td class='num'>${line.quote_each(draft.labor_rates):,.2f}</td>"
            f"<td>{escape(line.code)}</td>"
            f"<td class='num'>${line.tax_each:,.2f}</td>"
            f"<td class='num'>${line.sell_total(draft.labor_rates):,.2f}</td>"
            "</tr>"
        )
    warning_html = "".join(f"<li>{escape(item)}</li>" for item in warnings)
    notes = escape(draft.general_notes).replace("\n", "<br>")
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>JTI Quote Preview</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 36px; color: #111; }}
h1 {{ margin: 0; }} .draft {{ color: #9b1c1c; font-weight: bold; font-size: 18px; }}
.meta {{ margin: 14px 0 20px; }} table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ border-bottom: 1px solid #bbb; padding: 7px 5px; vertical-align: top; }}
th {{ text-align: left; background: #eee; }} .num {{ text-align: right; white-space: nowrap; }}
.total {{ text-align: right; font-size: 18px; font-weight: bold; margin-top: 16px; }}
.warning {{ border: 2px solid #9b1c1c; padding: 12px; margin: 16px 0; background: #fff5f5; }}
</style></head><body>
<div class='draft'>{'DRAFT — NOT FOR SUBMISSION' if warnings else 'READY FOR ESTIMATOR FINAL REVIEW'}</div>
<h1>JTI Millwork — Quotation Preview</h1>
<div class='meta'><b>Project:</b> {escape(draft.project_title)}<br>
<b>Quote:</b> {escape(draft.quote_number)} &nbsp; <b>Date:</b> {escape(draft.quote_date)} &nbsp;
<b>Terms:</b> {escape(draft.terms or 'not set')} &nbsp; <b>Rep:</b> {escape(draft.rep or 'not set')}</div>
{f"<div class='warning'><b>Items requiring attention:</b><ul>{warning_html}</ul></div>" if warnings else ''}
<table><thead><tr><th>Item</th><th>Description</th><th>Qty</th><th>Each</th><th>Code</th><th>Tax Each</th><th>Amount</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div class='total'>Quote Total: ${draft.total:,.2f}</div>
<h3>General Notes</h3><div>{notes or 'No general notes entered.'}</div>
</body></html>"""


def write_quote_preview(root: str | Path, draft: EstimateDraft) -> tuple[Path, Path]:
    root = Path(root)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / QUOTE_PREVIEW_HTML
    pdf_path = output / QUOTE_PREVIEW_PDF
    html_path.write_text(quote_preview_html(draft), encoding="utf-8")
    _write_quote_pdf(pdf_path, draft)
    return html_path, pdf_path


def _write_quote_pdf(path: Path, draft: EstimateDraft) -> None:
    doc = fitz.open()
    warnings = draft.warnings()

    def new_page() -> tuple[fitz.Page, float]:
        page = doc.new_page(width=612, height=792)
        page.insert_text((40, 42), "JTI Millwork - Quotation Preview", fontsize=16, fontname="helv")
        page.insert_text((40, 62), "DRAFT - NOT FOR SUBMISSION" if warnings else "READY FOR ESTIMATOR FINAL REVIEW", fontsize=10, fontname="helv")
        return page, 86.0

    page, y = new_page()
    meta = [
        f"Project: {draft.project_title}",
        f"Quote: {draft.quote_number}    Date: {draft.quote_date}",
        f"Terms: {draft.terms or 'not set'}    Rep: {draft.rep or 'not set'}",
    ]
    for text in meta:
        page.insert_text((40, y), text[:105], fontsize=9, fontname="helv")
        y += 14
    y += 8
    if warnings:
        page.insert_text((40, y), "REVIEW REQUIRED:", fontsize=9, fontname="hebo")
        y += 14
        for warning in warnings[:8]:
            rect = fitz.Rect(48, y - 9, 570, y + 24)
            used = page.insert_textbox(rect, "- " + warning, fontsize=8, fontname="helv")
            y += 24 if used >= 0 else 34
        y += 6

    for line in draft.lines:
        if not line.included:
            continue
        if y > 700:
            page, y = new_page()
        price = line.sell_total(draft.labor_rates)
        heading = f"{line.item}. Qty {line.quantity:g}    Each ${line.quote_each(draft.labor_rates):,.2f}    Tax Each ${line.tax_each:,.2f}    Amount ${price:,.2f}"
        page.insert_text((40, y), heading[:115], fontsize=8.5, fontname="hebo")
        y += 12
        rect = fitz.Rect(48, y - 8, 570, y + 44)
        page.insert_textbox(rect, line.description, fontsize=8, fontname="helv")
        y += 46

    if y > 690:
        page, y = new_page()
    page.insert_text((350, y), f"Quote Total: ${draft.total:,.2f}", fontsize=12, fontname="hebo")
    y += 28
    if draft.general_notes:
        page.insert_text((40, y), "General Notes", fontsize=9, fontname="hebo")
        y += 12
        page.insert_textbox(fitz.Rect(40, y, 570, 750), draft.general_notes, fontsize=8, fontname="helv")

    doc.save(path)
    doc.close()
