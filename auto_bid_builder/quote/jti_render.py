from __future__ import annotations

from html import escape
from pathlib import Path

import fitz

from auto_bid_builder.estimate.draft import EstimateDraft


JTI_QUOTE_HTML = "jti_quote.html"
JTI_QUOTE_PDF = "jti_quote.pdf"


def _status(draft: EstimateDraft) -> str:
    return "DRAFT - NOT FOR SUBMISSION" if draft.warnings() else "ESTIMATOR REVIEW COMPLETE"


def _html(draft: EstimateDraft) -> str:
    rows: list[str] = []
    for line in draft.lines:
        if not line.included:
            continue
        rows.append(
            "<tr>"
            f"<td class='item'>{line.item}</td>"
            f"<td class='desc'>{escape(line.description)}</td>"
            f"<td class='num'>{line.quantity:g}</td>"
            f"<td class='num'>{line.quote_each(draft.labor_rates):,.2f}</td>"
            f"<td class='code'>{escape(line.code)}</td>"
            f"<td class='num'>{line.tax_each:,.2f}</td>"
            f"<td class='num'>{line.sell_total(draft.labor_rates):,.2f}</td>"
            "</tr>"
        )
    warnings = "".join(f"<li>{escape(w)}</li>" for w in draft.warnings())
    notes = escape(draft.general_notes).replace("\n", "<br>") or ""
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>JTI Quote</title>
<style>
@page {{ size: letter; margin: 0.45in; }}
body {{ font-family: Arial, Helvetica, sans-serif; color:#000; font-size:10px; margin:0; }}
.header {{ display:grid; grid-template-columns: 1fr 1fr; align-items:end; border-bottom:2px solid #000; padding-bottom:7px; }}
.company {{ font-size:19px; font-weight:700; letter-spacing:.2px; }}
.quote {{ text-align:right; font-size:20px; font-weight:700; }}
.status {{ margin:7px 0; font-weight:700; color:#8b0000; }}
.meta {{ width:100%; border-collapse:collapse; margin:7px 0 11px; }}
.meta td {{ padding:2px 7px 2px 0; vertical-align:top; }}
.meta .label {{ font-weight:700; width:55px; }}
table.lines {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
table.lines th {{ border-top:1px solid #000; border-bottom:1px solid #000; padding:4px 3px; text-align:left; font-size:9px; }}
table.lines td {{ padding:5px 3px; vertical-align:top; border-bottom:1px solid #bbb; }}
.item {{ width:4%; }} .desc {{ width:52%; }} .code {{ width:7%; text-align:center; }} .num {{ text-align:right; white-space:nowrap; }}
.total {{ margin-top:9px; border-top:2px solid #000; padding-top:5px; text-align:right; font-weight:700; font-size:13px; }}
.notes {{ margin-top:14px; }} .notes h3 {{ font-size:10px; margin:0 0 4px; }}
.warning {{ margin:10px 0; border:1px solid #8b0000; padding:7px; }}
.footer {{ margin-top:20px; font-size:8px; text-align:center; border-top:1px solid #000; padding-top:5px; }}
</style></head><body>
<div class='header'><div class='company'>JEFFREY TROTT INDUSTRIES</div><div class='quote'>QUOTE</div></div>
<div class='status'>{_status(draft)}</div>
<table class='meta'>
<tr><td class='label'>Quote</td><td>{escape(draft.quote_number or 'DRAFT')}</td><td class='label'>Date</td><td>{escape(draft.quote_date)}</td></tr>
<tr><td class='label'>Project</td><td colspan='3'>{escape(draft.project_title)}</td></tr>
<tr><td class='label'>Terms</td><td>{escape(draft.terms or '')}</td><td class='label'>Rep</td><td>{escape(draft.rep or '')}</td></tr>
</table>
{f"<div class='warning'><b>Internal review required before submission:</b><ul>{warnings}</ul></div>" if warnings else ''}
<table class='lines'>
<thead><tr><th style='width:4%'>Item</th><th style='width:52%'>Description</th><th style='width:6%;text-align:right'>Qty</th><th style='width:10%;text-align:right'>Each</th><th style='width:7%;text-align:center'>Code</th><th style='width:9%;text-align:right'>Tax Each</th><th style='width:12%;text-align:right'>Amount</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<div class='total'>Quote Total&nbsp;&nbsp;&nbsp; ${draft.total:,.2f}</div>
<div class='notes'><h3>General Notes</h3>{notes}</div>
<div class='footer'>JEFFREY TROTT INDUSTRIES</div>
</body></html>"""


def write_jti_quote(root: str | Path, draft: EstimateDraft) -> tuple[Path, Path]:
    """Write customer-facing output in the familiar JTI quote layout.

    Internal labor/material math, source references, confidence notes, and sliders stay
    in the estimator UI. The customer-facing quote intentionally remains lean: Item,
    Description, Qty, Each, Code, Tax Each, Amount, General Notes, and Quote Total.
    """
    root = Path(root)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / JTI_QUOTE_HTML
    pdf_path = output / JTI_QUOTE_PDF
    html_path.write_text(_html(draft), encoding="utf-8")
    _write_pdf(pdf_path, draft)
    return html_path, pdf_path


def _write_pdf(path: Path, draft: EstimateDraft) -> None:
    doc = fitz.open()
    warnings = draft.warnings()

    def new_page(page_no: int) -> tuple[fitz.Page, float]:
        page = doc.new_page(width=612, height=792)
        page.insert_text((36, 38), "JEFFREY TROTT INDUSTRIES", fontsize=15, fontname="hebo")
        page.insert_text((516, 38), "QUOTE", fontsize=15, fontname="hebo")
        page.draw_line((36, 46), (576, 46), width=1.4)
        page.insert_text((36, 62), _status(draft), fontsize=8.5, fontname="hebo")
        page.insert_text((36, 79), f"Quote: {draft.quote_number or 'DRAFT'}", fontsize=8.5)
        page.insert_text((184, 79), f"Date: {draft.quote_date}", fontsize=8.5)
        page.insert_text((335, 79), f"Terms: {draft.terms or ''}", fontsize=8.5)
        page.insert_text((474, 79), f"Rep: {draft.rep or ''}", fontsize=8.5)
        page.insert_text((36, 95), f"Project: {draft.project_title}"[:105], fontsize=8.5)
        y = 116.0
        if page_no == 1 and warnings:
            page.insert_text((36, y), "INTERNAL REVIEW REQUIRED BEFORE SUBMISSION", fontsize=8, fontname="hebo")
            y += 12
        headers = ((36, "Item"), (64, "Description"), (377, "Qty"), (414, "Each"), (468, "Code"), (505, "Tax Each"), (555, "Amount"))
        page.draw_line((36, y), (576, y), width=0.8)
        y += 11
        for x, text in headers:
            page.insert_text((x, y), text, fontsize=7.5, fontname="hebo")
        y += 5
        page.draw_line((36, y), (576, y), width=0.8)
        return page, y + 12

    page, y = new_page(1)
    page_no = 1
    for line in draft.lines:
        if not line.included:
            continue
        desc_rect = fitz.Rect(64, y - 8, 370, y + 36)
        needed = max(24.0, 12.0 + 9.0 * max(1, len(line.description) // 58))
        if y + needed > 720:
            page_no += 1
            page, y = new_page(page_no)
            desc_rect = fitz.Rect(64, y - 8, 370, y + 36)
        page.insert_text((36, y), str(line.item), fontsize=7.5)
        page.insert_textbox(desc_rect, line.description, fontsize=7.5, fontname="helv")
        page.insert_text((402, y), f"{line.quantity:g}", fontsize=7.5)
        page.insert_text((412, y), f"{line.quote_each(draft.labor_rates):,.2f}", fontsize=7.5)
        page.insert_text((470, y), line.code[:7], fontsize=7.5)
        page.insert_text((507, y), f"{line.tax_each:,.2f}", fontsize=7.5)
        amount = f"{line.sell_total(draft.labor_rates):,.2f}"
        page.insert_text((536, y), amount, fontsize=7.5)
        y += needed
        page.draw_line((36, y - 5), (576, y - 5), width=0.25)

    if y > 665:
        page_no += 1
        page, y = new_page(page_no)
    page.draw_line((390, y + 2), (576, y + 2), width=1.2)
    page.insert_text((442, y + 17), "Quote Total", fontsize=9, fontname="hebo")
    page.insert_text((526, y + 17), f"${draft.total:,.2f}", fontsize=9, fontname="hebo")
    y += 39
    page.insert_text((36, y), "General Notes", fontsize=8, fontname="hebo")
    y += 10
    if draft.general_notes:
        page.insert_textbox(fitz.Rect(36, y, 576, 742), draft.general_notes, fontsize=7.5)
    page.draw_line((36, 755), (576, 755), width=0.5)
    page.insert_text((246, 769), "JEFFREY TROTT INDUSTRIES", fontsize=6.5)
    doc.save(path)
    doc.close()
