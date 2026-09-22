from __future__ import annotations

from html import escape
from pathlib import Path
import shutil

import fitz

from auto_bid_builder.estimate.draft import EstimateDraft


JTI_QUOTE_HTML = "jti_quote.html"
JTI_QUOTE_PDF = "jti_quote.pdf"
LEGACY_PREVIEW_HTML = "quote_preview.html"
LEGACY_PREVIEW_PDF = "quote_preview.pdf"
_FOOTER_1 = "JEFFREY TROTT INDUSTRIES, INC."
_FOOTER_2 = "1934 NORTH ENTERPRISE STREET"
_FOOTER_3 = "PH 714 974-1008"
_FOOTER_4 = "CONTRACTORS LICENSE CA 527317"
_FOOTER_5 = "ORANGE, CA 92865"
_FOOTER_6 = "FX 714 974-3723"


def _status(draft: EstimateDraft) -> str:
    return "DRAFT - NOT FOR SUBMISSION" if draft.warnings() else ""


def _line_block_html(draft: EstimateDraft, line) -> str:
    return (
        "<div class='lineblock'>"
        "<div class='bar'><span>Item</span><span>Description</span><span>Qty</span><span>Each</span><span>Code</span><span>Tax Each</span><span>Amount</span></div>"
        "<div class='row'>"
        f"<span class='center'>{line.item}</span>"
        f"<span>{escape(line.description)}</span>"
        f"<span class='num'>{line.quantity:g}</span>"
        f"<span class='num'>{line.quote_each(draft.labor_rates):,.2f}</span>"
        f"<span class='center'>{escape(line.code)}</span>"
        f"<span class='num'>{line.tax_each:,.2f}</span>"
        f"<span class='num'>{line.sell_total(draft.labor_rates):,.2f}</span>"
        "</div></div>"
    )


def _html(draft: EstimateDraft) -> str:
    blocks = "".join(_line_block_html(draft, line) for line in draft.lines if line.included)
    warnings = "".join(f"<li>{escape(w)}</li>" for w in draft.warnings())
    notes = escape(draft.general_notes).replace("\n", "<br>") or ""
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>JTI Quotation</title>
<style>
@page {{ size: letter; margin: 0.45in; }}
body {{ font-family: Arial, Helvetica, sans-serif; color:#000; font-size:10px; margin:0; }}
.top {{ position:relative; height:92px; }}
.title {{ position:absolute; left:3px; top:43px; font-size:20px; font-weight:700; }}
.logo {{ position:absolute; left:43%; top:0; width:140px; text-align:center; }}
.logo .arch {{ font-size:7px; letter-spacing:2px; }} .logo .jti {{ font-family:serif; font-size:52px; line-height:48px; }} .logo .mill {{ font-size:8px; letter-spacing:7px; }}
.meta-head,.meta-row {{ display:grid; grid-template-columns: 13% 18% 29% 13% 17% 10%; }}
.meta-head {{ background:#ddd; border:1px solid #333; font-size:8px; text-align:center; }}
.meta-row {{ font-size:12px; font-weight:700; padding:4px 0 10px; }}
.meta-row > div {{ text-align:center; }}
.people-head {{ display:grid; grid-template-columns: 1fr 1fr 1fr; background:#ddd; border:1px solid #333; font-size:8px; text-align:center; }}
.people-row {{ display:grid; grid-template-columns:1fr 1fr 1fr; min-height:76px; padding:8px 48px 0; gap:45px; }}
.rule {{ border-top:1px solid #000; margin:8px 0 14px; }}
.status {{ font-weight:700; color:#8b0000; margin-bottom:8px; }}
.warning {{ border:1px solid #8b0000; padding:6px 10px; margin:6px 0 10px; }}
.lineblock {{ margin:0 0 16px; page-break-inside:avoid; }}
.bar,.row {{ display:grid; grid-template-columns: 7% 49% 7% 12% 8% 9% 8%; }}
.bar {{ background:#ddd; border:1px solid #333; font-size:8px; padding:2px 0; }}
.bar span {{ text-align:center; }} .bar span:nth-child(2) {{ text-align:left; }}
.row {{ padding:5px 0 1px; font-size:10px; }}
.row span {{ padding:0 4px; }} .num {{ text-align:right; white-space:nowrap; }} .center {{ text-align:center; }}
.notesbar {{ display:grid; grid-template-columns:1fr 180px; background:#ddd; border:1px solid #333; font-size:9px; font-weight:700; padding:3px 8px; margin-top:6px; }}
.notesbar div:last-child {{ text-align:right; }}
.notesrow {{ display:grid; grid-template-columns:1fr 180px; padding:10px 24px; }}
.total {{ text-align:right; font-weight:700; font-size:16px; }}
.footer {{ margin-top:36px; border-top:1px solid #000; padding-top:7px; display:grid; grid-template-columns:1fr 1fr 1fr; text-align:center; font-size:8px; line-height:13px; }}
</style></head><body>
<div class='top'><div class='title'>QUOTATION</div><div class='logo'><div class='arch'>ARCHITECTURAL</div><div class='jti'>JTI</div><div class='mill'>MILLWORK</div></div></div>
<div class='meta-head'><div>Number</div><div>Date</div><div>Description</div><div>Completion</div><div>Terms</div><div>Rep</div></div>
<div class='meta-row'><div>{escape(draft.quote_number or 'DRAFT')}</div><div>{escape(draft.quote_date)}</div><div>{escape(draft.project_title)}</div><div></div><div>{escape(draft.terms or '')}</div><div>{escape(draft.rep or '')}</div></div>
<div class='people-head'><div>Proposed To</div><div>Job Site</div><div>Contact</div></div>
<div class='people-row'><div></div><div>{escape(draft.project_title)}</div><div></div></div>
<div class='rule'></div>
{f"<div class='status'>{_status(draft)}</div><div class='warning'><b>Internal review required:</b><ul>{warnings}</ul></div>" if warnings else ''}
{blocks}
<div class='notesbar'><div>General Notes</div><div>Quote Total</div></div>
<div class='notesrow'><div>{notes}</div><div class='total'>{draft.total:,.2f}</div></div>
<div class='footer'><div>{_FOOTER_1}<br>{_FOOTER_4}</div><div>{_FOOTER_2}<br>{_FOOTER_5}</div><div>{_FOOTER_3}<br>{_FOOTER_6}</div></div>
</body></html>"""


def write_jti_quote(root: str | Path, draft: EstimateDraft) -> tuple[Path, Path]:
    """Write customer-facing JTI output and refresh the private AI-review package."""
    root = Path(root)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / JTI_QUOTE_HTML
    pdf_path = output / JTI_QUOTE_PDF
    html_text = _html(draft)
    html_path.write_text(html_text, encoding="utf-8")
    (output / LEGACY_PREVIEW_HTML).write_text(html_text, encoding="utf-8")
    _write_pdf(pdf_path, draft)
    shutil.copy2(pdf_path, output / LEGACY_PREVIEW_PDF)

    # Local-only bundle for a second-pass AI/human audit. Import lazily to avoid a
    # module cycle and to keep quote rendering usable outside a workspace.
    try:
        from auto_bid_builder.bid_workspace import build_ai_review_package
        if (root / "bid_workspace.json").exists():
            build_ai_review_package(root)
    except Exception:
        # Quote generation must never fail merely because packaging did.
        pass
    return html_path, pdf_path


def _draw_logo(page: fitz.Page) -> None:
    page.insert_text((271, 24), "ARCHITECTURAL", fontsize=5.5, fontname="helv")
    page.insert_text((272, 60), "JTI", fontsize=36, fontname="tiro")
    page.insert_text((277, 73), "M I L L W O R K", fontsize=4.5, fontname="helv")


def _footer(page: fitz.Page) -> None:
    page.draw_line((12, 752), (600, 752), width=0.6)
    page.insert_text((82, 767), _FOOTER_1, fontsize=6.4)
    page.insert_text((89, 778), _FOOTER_4, fontsize=6.4)
    page.insert_text((267, 767), _FOOTER_2, fontsize=6.4)
    page.insert_text((302, 778), _FOOTER_5, fontsize=6.4)
    page.insert_text((450, 767), _FOOTER_3, fontsize=6.4)
    page.insert_text((452, 778), _FOOTER_6, fontsize=6.4)


def _gray_bar(page: fitz.Page, y: float, labels: tuple[str, ...]) -> None:
    page.draw_rect(fitz.Rect(12, y, 600, y + 14), color=(0, 0, 0), fill=(0.86, 0.86, 0.86), width=0.6)
    xs = (28, 68, 337, 397, 452, 497, 563)
    for x, label in zip(xs, labels):
        page.insert_text((x, y + 10), label, fontsize=6.2, fontname="helv")


def _write_pdf(path: Path, draft: EstimateDraft) -> None:
    doc = fitz.open()
    lines = [line for line in draft.lines if line.included]
    page_no = 0
    index = 0

    while index < len(lines) or page_no == 0:
        page_no += 1
        page = doc.new_page(width=612, height=792)
        _draw_logo(page)
        if page_no == 1:
            page.insert_text((40, 79), "QUOTATION", fontsize=16, fontname="hebo")
            page.draw_rect(fitz.Rect(12, 108, 600, 122), color=(0, 0, 0), fill=(0.86, 0.86, 0.86), width=0.6)
            labels = ((28, "Number"), (145, "Date"), (286, "Description"), (397, "Completion"), (500, "Terms"), (570, "Rep"))
            for x, text in labels:
                page.insert_text((x, 118), text, fontsize=6.2)
            page.insert_text((37, 138), draft.quote_number or "DRAFT", fontsize=10, fontname="hebo")
            page.insert_text((115, 138), draft.quote_date, fontsize=9, fontname="hebo")
            page.insert_text((264, 138), draft.project_title[:30], fontsize=9)
            page.insert_text((478, 138), draft.terms or "", fontsize=9)
            page.insert_text((568, 138), draft.rep or "", fontsize=9)
            page.draw_rect(fitz.Rect(12, 151, 600, 165), color=(0, 0, 0), fill=(0.86, 0.86, 0.86), width=0.6)
            for x, text in ((52, "Proposed To"), (252, "Job Site"), (483, "Contact")):
                page.insert_text((x, 161), text, fontsize=6.2)
            page.insert_text((252, 184), draft.project_title[:38], fontsize=9)
            page.draw_line((12, 248), (600, 248), width=0.7)
            y = 262.0
            if draft.warnings():
                page.insert_text((12, y), "DRAFT - NOT FOR SUBMISSION", fontsize=7, fontname="hebo")
                y += 12
        else:
            page.insert_text((40, 79), f"QUOTE {draft.quote_number or 'DRAFT'}", fontsize=13, fontname="hebo")
            page.insert_text((139, 79), f"(Page {page_no})", fontsize=7)
            page.draw_line((12, 96), (600, 96), width=0.7)
            y = 113.0

        while index < len(lines):
            line = lines[index]
            text_lines = max(1, (len(line.description) + 57) // 58)
            block_h = max(45.0, 28.0 + text_lines * 9.5)
            reserve_for_notes = 125.0 if index == len(lines) - 1 else 0.0
            if y + block_h + reserve_for_notes > 730:
                break
            _gray_bar(page, y, ("Item", "Description", "Qty", "Each", "Code", "Tax Each", "Amount"))
            y += 22
            page.insert_text((36, y), str(line.item), fontsize=8)
            page.insert_textbox(fitz.Rect(68, y - 8, 332, y + block_h - 12), line.description, fontsize=8.2, fontname="helv")
            page.insert_text((338, y), f"{line.quantity:g}", fontsize=8)
            page.insert_text((385, y), f"{line.quote_each(draft.labor_rates):,.2f}", fontsize=8)
            page.insert_text((451, y), line.code[:7], fontsize=8)
            page.insert_text((489, y), f"{line.tax_each:,.2f}", fontsize=8)
            page.insert_text((548, y), f"{line.sell_total(draft.labor_rates):,.2f}", fontsize=8)
            y += block_h - 6
            index += 1

        if index >= len(lines):
            if y > 620:
                _footer(page)
                page_no += 1
                page = doc.new_page(width=612, height=792)
                _draw_logo(page)
                page.insert_text((40, 79), f"QUOTE {draft.quote_number or 'DRAFT'}", fontsize=13, fontname="hebo")
                page.insert_text((139, 79), f"(Page {page_no})", fontsize=7)
                page.draw_line((12, 96), (600, 96), width=0.7)
                y = 113.0
            page.draw_rect(fitz.Rect(12, y, 600, y + 15), color=(0, 0, 0), fill=(0.86, 0.86, 0.86), width=0.6)
            page.insert_text((31, y + 11), "General Notes", fontsize=7, fontname="hebo")
            page.insert_text((546, y + 11), "Quote Total", fontsize=7, fontname="hebo")
            y += 26
            if draft.general_notes:
                page.insert_textbox(fitz.Rect(31, y - 5, 455, y + 70), draft.general_notes, fontsize=8.2)
            page.insert_text((531, y + 4), f"{draft.total:,.2f}", fontsize=12, fontname="hebo")
        _footer(page)

    doc.save(path)
    doc.close()
