from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import shutil
import re
from urllib.parse import urlsplit

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


@dataclass(frozen=True)
class QuoteProjectContext:
    proposed_to: str = ""
    job_site_lines: tuple[str, ...] = ()
    contact_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuoteReferencePage:
    source_path: Path
    source_name: str
    page_number: int
    sheet: str = ""
    item_numbers: tuple[int, ...] = ()
    source_refs: tuple[str, ...] = ()


def _normalize_ref(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _find_bid_document(root: Path, source_name: str) -> Path | None:
    bid_docs = root / "bid_docs"
    if not bid_docs.exists():
        return None
    exact = (bid_docs / source_name).resolve()
    if exact.is_relative_to(bid_docs.resolve()) and exact.is_file():
        return exact
    wanted = source_name.strip().lower()
    matches = [path for path in bid_docs.rglob("*") if path.is_file() and path.name.lower() == wanted]
    return matches[0] if len(matches) == 1 else None


def _reference_pages(root: Path, draft: EstimateDraft) -> tuple[QuoteReferencePage, ...]:
    """Resolve estimate source refs back to the exact PDF pages in bid_docs."""
    review_path = root / "output" / "bid_review.json"
    review_rows: list[dict] = []
    if review_path.exists():
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            review_rows = [row for row in payload.get("pages", []) if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            review_rows = []

    index: dict[str, dict] = {}
    for row in review_rows:
        source = str(row.get("source") or "").strip()
        if not source:
            continue
        page_number = int(row.get("page") or 0)
        sheet = str(row.get("sheet") or "").strip()
        if sheet:
            index[_normalize_ref(f"{source} / {sheet}")] = row
        if page_number > 0:
            index[_normalize_ref(f"{source} / page {page_number}")] = row

    grouped: dict[tuple[str, int], dict] = {}
    for line in draft.lines:
        if not line.included:
            continue
        for raw_ref in line.source_refs:
            ref = str(raw_ref or "").strip()
            if not ref:
                continue
            row = index.get(_normalize_ref(ref))
            source_name = ""
            page_number = 0
            sheet = ""
            if row is not None:
                source_name = str(row.get("source") or "").strip()
                page_number = int(row.get("page") or 0)
                sheet = str(row.get("sheet") or "").strip()
            else:
                # Support manually entered "file.pdf / page N" references even
                # when the bid review JSON is unavailable.
                match = re.match(r"^(.*?)\s*/\s*page\s+(\d+)\s*$", ref, re.I)
                if match:
                    source_name = match.group(1).strip()
                    page_number = int(match.group(2))

            if not source_name or page_number <= 0:
                continue
            source_path = _find_bid_document(root, source_name)
            if source_path is None or source_path.suffix.lower() != ".pdf":
                continue
            key = (str(source_path.resolve()).lower(), page_number)
            entry = grouped.setdefault(
                key,
                {
                    "source_path": source_path,
                    "source_name": source_name,
                    "page_number": page_number,
                    "sheet": sheet,
                    "items": [],
                    "refs": [],
                },
            )
            if line.item not in entry["items"]:
                entry["items"].append(line.item)
            if ref not in entry["refs"]:
                entry["refs"].append(ref)
            if sheet and not entry["sheet"]:
                entry["sheet"] = sheet

    pages: list[QuoteReferencePage] = []
    for entry in grouped.values():
        try:
            with fitz.open(entry["source_path"]) as source_doc:
                if not (1 <= int(entry["page_number"]) <= source_doc.page_count):
                    continue
        except Exception:
            continue
        pages.append(
            QuoteReferencePage(
                source_path=entry["source_path"],
                source_name=entry["source_name"],
                page_number=int(entry["page_number"]),
                sheet=str(entry["sheet"] or ""),
                item_numbers=tuple(sorted(int(x) for x in entry["items"])),
                source_refs=tuple(entry["refs"]),
            )
        )
    pages.sort(key=lambda row: (min(row.item_numbers or (999999,)), row.source_name.lower(), row.page_number))
    return tuple(pages)


def _reference_text(line) -> str:
    refs = [str(ref).strip() for ref in line.source_refs if str(ref).strip()]
    return " | ".join(refs)


def _workspace_opportunity(root: Path) -> dict:
    manifest_path = root / "bid_workspace.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    row = manifest.get("opportunity") or {}
    if isinstance(row, dict) and isinstance(row.get("opportunity"), dict):
        return row["opportunity"]
    return row if isinstance(row, dict) else {}


def _quote_project_context(root: Path, draft: EstimateDraft) -> QuoteProjectContext:
    opportunity = _workspace_opportunity(root)
    if not opportunity:
        return QuoteProjectContext(job_site_lines=(draft.project_title,))

    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), dict) else {}
    proposed_to = str(opportunity.get("organization") or "").strip()

    job_lines: list[str] = []
    title = str(opportunity.get("title") or draft.project_title or "").strip()
    if title:
        job_lines.append(title)

    street = str(opportunity.get("street_address") or metadata.get("street_address") or "").strip()
    if street:
        job_lines.append(street)

    city = str(opportunity.get("city") or "").strip()
    state = str(opportunity.get("state") or "").strip()
    postal = str(opportunity.get("postal_code") or "").strip()
    city_state = ", ".join(x for x in (city, state) if x)
    location = " ".join(x for x in (city_state, postal) if x)
    if location:
        job_lines.append(location)
    elif metadata.get("location_text"):
        job_lines.append(str(metadata.get("location_text")).strip())

    source = str(opportunity.get("source") or "").strip()
    listing_url = str(opportunity.get("url") or "").strip()
    domain = ""
    if listing_url:
        try:
            domain = (urlsplit(listing_url).hostname or "").removeprefix("www.")
        except ValueError:
            domain = ""
    due = str(opportunity.get("bid_due_date") or "").strip()
    if due:
        job_lines.append(f"Bid due: {due}")

    if source:
        source_text = f"Source: {source}"
        if domain and domain.lower() not in source.lower():
            source_text += f" | {domain}"
        job_lines.append(source_text)

    identifier = (
        metadata.get("solicitation_number")
        or metadata.get("project_number")
        or opportunity.get("external_id")
    )
    if identifier:
        job_lines.append(f"Solicitation/Event: {identifier}")

    contact = metadata.get("primary_contact") if isinstance(metadata.get("primary_contact"), dict) else {}
    if not contact:
        contact = {
            "name": metadata.get("contact_name") or metadata.get("poc_name"),
            "title": metadata.get("contact_title") or metadata.get("poc_title"),
            "email": metadata.get("contact_email") or metadata.get("poc_email"),
            "phone": metadata.get("contact_phone") or metadata.get("poc_phone"),
        }

    contact_lines: list[str] = []
    name = str(contact.get("name") or contact.get("fullname") or "").strip()
    title_value = str(contact.get("title") or "").strip()
    if name:
        contact_lines.append(name)
    if title_value:
        contact_lines.append(title_value)
    email = str(contact.get("email") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    if email:
        contact_lines.append(email)
    if phone:
        contact_lines.append(phone)

    return QuoteProjectContext(
        proposed_to=proposed_to,
        job_site_lines=tuple(job_lines[:6]),
        contact_lines=tuple(contact_lines[:4]),
    )


def _html_lines(values: tuple[str, ...]) -> str:
    return "<br>".join(escape(str(value)) for value in values if str(value).strip())


def _status(draft: EstimateDraft) -> str:
    return "DRAFT - NOT FOR SUBMISSION" if draft.warnings() else ""


def _line_block_html(draft: EstimateDraft, line) -> str:
    reference = _reference_text(line)
    description = escape(line.description)
    if reference:
        description += f"<div class='ref'>Ref: {escape(reference)}</div>"
    return (
        "<div class='lineblock'>"
        "<div class='bar'><span>Item</span><span>Description</span><span>Qty</span><span>Each</span><span>Code</span><span>Tax Each</span><span>Amount</span></div>"
        "<div class='row'>"
        f"<span class='center'>{line.item}</span>"
        f"<span>{description}</span>"
        f"<span class='num'>{line.quantity:g}</span>"
        f"<span class='num'>{line.quote_each(draft.labor_rates):,.2f}</span>"
        f"<span class='center'>{escape(line.code)}</span>"
        f"<span class='num'>{line.tax_each:,.2f}</span>"
        f"<span class='num'>{line.sell_total(draft.labor_rates):,.2f}</span>"
        "</div></div>"
    )


def _html(draft: EstimateDraft, context: QuoteProjectContext | None = None) -> str:
    context = context or QuoteProjectContext(job_site_lines=(draft.project_title,))
    blocks = "".join(_line_block_html(draft, line) for line in draft.lines if line.included)
    warnings = "".join(f"<li>{escape(w)}</li>" for w in draft.warnings())
    notes = escape(draft.general_notes).replace("\n", "<br>") or ""
    proposed_to = escape(context.proposed_to)
    job_site = _html_lines(context.job_site_lines)
    contact = _html_lines(context.contact_lines)
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
.people-row {{ display:grid; grid-template-columns:1fr 1fr 1fr; min-height:92px; padding:8px 24px 0; gap:28px; font-size:9px; line-height:13px; }}
.rule {{ border-top:1px solid #000; margin:8px 0 14px; }}
.status {{ font-weight:700; color:#8b0000; margin-bottom:8px; }}
.warning {{ border:1px solid #8b0000; padding:6px 10px; margin:6px 0 10px; }}
.lineblock {{ margin:0 0 16px; page-break-inside:avoid; }}
.bar,.row {{ display:grid; grid-template-columns: 7% 49% 7% 12% 8% 9% 8%; }}
.bar {{ background:#ddd; border:1px solid #333; font-size:8px; padding:2px 0; }}
.bar span {{ text-align:center; }} .bar span:nth-child(2) {{ text-align:left; }}
.row {{ padding:5px 0 1px; font-size:10px; }}
.row span {{ padding:0 4px; }} .ref {{ margin-top:3px; font-size:7px; color:#444; }} .num {{ text-align:right; white-space:nowrap; }} .center {{ text-align:center; }}
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
<div class='people-row'><div>{proposed_to}</div><div>{job_site}</div><div>{contact}</div></div>
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
    if (root / "bid_workspace.json").exists():
        from auto_bid_builder.validation.project_identity import check_workspace_project_identity
        identity = check_workspace_project_identity(root)
        if identity["status"] == "conflict":
            raise ValueError(
                "Quote blocked: project identity mismatch. "
                + "; ".join(identity["errors"])
                + " Move the wrong project PDFs to the correct bid workspace and reanalyze."
            )
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / JTI_QUOTE_HTML
    pdf_path = output / JTI_QUOTE_PDF
    context = _quote_project_context(root, draft)
    html_text = _html(draft, context)
    html_path.write_text(html_text, encoding="utf-8")
    (output / LEGACY_PREVIEW_HTML).write_text(html_text, encoding="utf-8")
    _write_pdf(pdf_path, draft, context, root=root)
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


def _write_pdf(
    path: Path,
    draft: EstimateDraft,
    context: QuoteProjectContext | None = None,
    *,
    root: Path | None = None,
) -> None:
    context = context or QuoteProjectContext(job_site_lines=(draft.project_title,))
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
            page.insert_textbox(
                fitz.Rect(31, 174, 190, 239),
                context.proposed_to,
                fontsize=7.5,
                fontname="helv",
                lineheight=1.15,
            )
            page.insert_textbox(
                fitz.Rect(215, 174, 408, 239),
                "\n".join(context.job_site_lines),
                fontsize=7.2,
                fontname="helv",
                lineheight=1.12,
            )
            page.insert_textbox(
                fitz.Rect(430, 174, 590, 239),
                "\n".join(context.contact_lines),
                fontsize=7.2,
                fontname="helv",
                lineheight=1.12,
            )
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
            reference = _reference_text(line)
            combined_text = line.description + (f"\nRef: {reference}" if reference else "")
            text_lines = max(1, (len(combined_text) + 57) // 58)
            block_h = max(45.0, 28.0 + text_lines * 9.5)
            reserve_for_notes = 125.0 if index == len(lines) - 1 else 0.0
            if y + block_h + reserve_for_notes > 730:
                break
            _gray_bar(page, y, ("Item", "Description", "Qty", "Each", "Code", "Tax Each", "Amount"))
            y += 22
            page.insert_text((36, y), str(line.item), fontsize=8)
            page.insert_textbox(fitz.Rect(68, y - 8, 332, y + block_h - 12), combined_text, fontsize=8.0, fontname="helv")
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

    if root is not None:
        references = _reference_pages(root, draft)
        for reference in references:
            try:
                source_doc = fitz.open(reference.source_path)
            except Exception:
                continue
            try:
                source_index = reference.page_number - 1
                if source_index < 0 or source_index >= source_doc.page_count:
                    continue
                source_page = source_doc[source_index]
                header_height = 30.0
                width = float(source_page.rect.width)
                height = float(source_page.rect.height)
                ref_page = doc.new_page(width=width, height=height + header_height)
                items = ", ".join(str(x) for x in reference.item_numbers)
                sheet = f" | Sheet {reference.sheet}" if reference.sheet else ""
                header = (
                    f"REFERENCE PAGE — Quote Item{'s' if len(reference.item_numbers) != 1 else ''} {items}"
                    f" | {reference.source_name}{sheet} | PDF page {reference.page_number}"
                )
                ref_page.insert_textbox(
                    fitz.Rect(12, 6, width - 12, header_height - 4),
                    header,
                    fontsize=8.5,
                    fontname="hebo",
                    align=fitz.TEXT_ALIGN_LEFT,
                )
                ref_page.show_pdf_page(
                    fitz.Rect(0, header_height, width, height + header_height),
                    source_doc,
                    source_index,
                    keep_proportion=True,
                    overlay=True,
                )
            finally:
                source_doc.close()

    doc.save(path)
    doc.close()
