from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from auto_bid_builder.ingest.pdf import extract_pdf_pages


_SPEC_RE = re.compile(r"\b(\d{2})\s+(\d{2})\s+(\d{2})\b")
_FINISH_RE = re.compile(r"\b(?:PL|WD|SS|ST|MTL|MEL|WC|GL|BR|ACT|GF|P)\d+[A-Za-z]?\b", re.I)
_DATE_RE = re.compile(r"\b(?:0?[1-9]|1[0-2])[/.](?:0?[1-9]|[12]\d|3[01])[/.](?:20)?\d{2}\b")
_ISO_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


@dataclass(frozen=True)
class ProjectDocument:
    source: str
    kind: str
    page_count: int
    project: str | None
    issue_date: str | None
    status: str | None
    spec_section: str | None
    responsible_contractor: str | None
    finish_codes: tuple[str, ...]
    review_actions: tuple[str, ...]
    flags: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.split()).strip(" :-") or None


def classify_document(filename: str, text: str) -> str:
    name = filename.lower()
    upper = text.upper()
    if "field measure" in name or "FIELD MEASURE" in upper:
        return "field_measure"
    if "shop drawing" in name or "SHOP DRAWINGS" in upper:
        return "shop_drawing_revision" if "revised" in name or "REVISED" in upper[:3000] else "shop_drawing"
    if "ask-" in name or re.search(r"\bASK-?\d+\b", upper):
        return "ask"
    if "rfi" in name or re.search(r"\bRFI\s*#?\s*\d+\b", upper):
        return "rfi"
    if "submittal" in name or "SUBMITTAL #" in upper or "SUBMITTAL PACKAGE" in upper:
        return "submittal"
    if "bulletin" in name or "BULLETIN" in upper:
        return "bulletin"
    if "quotation" in upper or " quote" in name:
        return "quote"
    return "drawing_or_project_document"


def _field(text: str, label: str, stop: str) -> str | None:
    m = re.search(rf"{label}\s*:?\s*(.+?)(?={stop}|$)", text, re.I | re.S)
    return _clean(m.group(1)) if m else None


def _project(text: str) -> str | None:
    m = re.search(r"\bProject\s*:\s*(.+?)(?:\n|\r)", text, re.I)
    if m:
        return _clean(m.group(1))
    m = re.search(r"\bProject Name\s*:\s*(.+?)(?:\n|\r)", text, re.I)
    return _clean(m.group(1)) if m else None


def _issue_date(text: str) -> str | None:
    for pattern in (
        r"ISSUE DATE\s*:\s*([^\n\r]+)",
        r"FIELD MEASURE\s+([^\n\r]+)",
        r"\bASK-?\d+[^\n\r]*?((?:0?\d|1[0-2])/(?:0?\d|[12]\d|3[01])/20\d{2})",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            value = _clean(m.group(1))
            if value:
                return value
    candidates = _ISO_DATE_RE.findall(text) + _DATE_RE.findall(text)
    return candidates[0] if candidates else None


def _status(text: str) -> str | None:
    m = re.search(r"\bSTATUS\s*:\s*(.+?)(?=\s+DATE CREATED|\s+ISSUE DATE|\n|\r)", text, re.I)
    if m:
        return _clean(m.group(1))
    # Treat an explicit reviewer directive with punctuation as stronger than a legend/checklist.
    if re.search(r"REVISE\s+AND\s+RESUBMIT\s*:", text, re.I):
        return "Revise and Resubmit"
    if re.search(r"\bNO\s+EXCEPTIONS\s+TAKEN\b", text, re.I):
        return "No Exceptions Taken"
    return None


def _spec_section(text: str) -> str | None:
    m = re.search(r"SPEC SECTION\s*:\s*(\d{2}\s+\d{2}\s+\d{2}(?:\s*-\s*[^\n\r]+)?)", text, re.I)
    if m:
        return _clean(m.group(1))
    m = _SPEC_RE.search(text)
    return " ".join(m.groups()) if m else None


def _responsible_contractor(text: str) -> str | None:
    m = re.search(
        r"RESPONSIBLE\s+CONTRACTOR\s*:\s*(.+?)(?=\s+RECEIVED FROM|\n\s*RECEIVED FROM)",
        text,
        re.I | re.S,
    )
    return _clean(m.group(1)) if m else None


def _review_actions(text: str) -> tuple[str, ...]:
    actions: list[str] = []
    if re.search(r"REVISE\s+AND\s+RESUBMIT\s*:", text, re.I):
        actions.append("revise_and_resubmit")
    if re.search(r"\bAPPROVED\s+AS\s+NOTED\b", text, re.I):
        actions.append("approved_as_noted")
    if re.search(r"\bNO\s+EXCEPTIONS\s+TAKEN\b", text, re.I):
        actions.append("no_exceptions_taken")
    if re.search(r"\bFURNISH\s+AS\s+CORRECTED\b", text, re.I):
        actions.append("furnish_as_corrected_present")
    if re.search(r"\bSUBMIT\s+SPECIFIED\s+ITEM\b", text, re.I):
        actions.append("submit_specified_item_present")
    if re.search(r"\bAPPROVED\s*:\s*(?:\n|\r|\s)+(?:PL|WD|SS|ST|MTL|MEL|WC|GL)", text, re.I):
        actions.append("partial_finish_approval")
    return tuple(dict.fromkeys(actions))


def _flags(kind: str, text: str, page_count: int) -> tuple[str, ...]:
    flags: list[str] = []
    upper = text.upper()
    if "FIELD MEASURE" in upper or "FIELD MEASURE" in kind.upper():
        flags.append("field_measure_evidence")
    if "V.I.F" in upper or "VERIFY IN FIELD" in upper:
        flags.append("verify_in_field")
    if "COORDINATE" in upper or "COORD." in upper:
        flags.append("coordination_required")
    if "REVISE AND RESUBMIT:" in upper:
        flags.append("unresolved_submittal_review")
    if "MATCH ADOTTA" in upper or "ADOTTA VENEER" in upper:
        flags.append("finish_match_requirement")
    if "BROOKSIDE VENEER" in upper:
        flags.append("veneer_resubmittal_required")
    if "CEILING HEIGHT" in upper or kind == "ask":
        flags.append("ceiling_or_ask_change")
    if kind == "rfi" and len(text.strip()) < 1200:
        flags.append("visual_rfi_review_required")
    if kind == "field_measure" and page_count > 1:
        flags.append("visual_field_dimensions_present")
    if kind == "shop_drawing_revision":
        flags.append("revised_fabrication_document")
    return tuple(dict.fromkeys(flags))


def extract_project_document(path: str | Path) -> ProjectDocument:
    path = Path(path)
    pages = extract_pdf_pages(path)
    text = "\n".join(page.text for page in pages)
    kind = classify_document(path.name, text)
    finishes = tuple(dict.fromkeys(m.group(0).upper() for m in _FINISH_RE.finditer(text)))
    return ProjectDocument(
        source=path.name,
        kind=kind,
        page_count=len(pages),
        project=_project(text),
        issue_date=_issue_date(text),
        status=_status(text),
        spec_section=_spec_section(text),
        responsible_contractor=_responsible_contractor(text),
        finish_codes=finishes,
        review_actions=_review_actions(text),
        flags=_flags(kind, text, len(pages)),
    )


def audit_project_folder(folder: str | Path) -> tuple[ProjectDocument, ...]:
    folder = Path(folder)
    files = [folder] if folder.is_file() else sorted(folder.glob("*.pdf"))
    return tuple(extract_project_document(path) for path in files)


def project_audit_markdown(documents: tuple[ProjectDocument, ...]) -> str:
    lines = ["# Project Document Audit", ""]
    unresolved = [d for d in documents if "unresolved_submittal_review" in d.flags]
    revised = [d for d in documents if d.kind in {"ask", "rfi", "shop_drawing_revision", "bulletin"}]
    field = [d for d in documents if d.kind == "field_measure"]
    lines += [
        f"Documents scanned: **{len(documents)}**",
        f"Revision/RFI/ASK documents: **{len(revised)}**",
        f"Field-measure packages: **{len(field)}**",
        f"Submittals requiring review/resubmittal signals: **{len(unresolved)}**",
        "",
        "## Review queue",
        "",
    ]
    queue = unresolved + [d for d in revised if d not in unresolved]
    if not queue:
        lines.append("No high-priority document-state signals were detected.")
    for doc in queue:
        lines.append(f"- **{doc.source}** — {doc.kind}; status: {doc.status or 'not reliably extracted'}; flags: {', '.join(doc.flags) or 'none'}")
    lines += ["", "## All documents", ""]
    for doc in documents:
        lines.append(
            f"- **{doc.source}** — {doc.kind}; pages {doc.page_count}; issue date {doc.issue_date or 'unknown'}; "
            f"spec {doc.spec_section or 'n/a'}; status {doc.status or 'unknown'}"
        )
    lines += [
        "",
        "> Review states are evidence signals, not contractual conclusions. Image-only markups and handwritten field dimensions remain human-review items unless a reliable text layer exists.",
        "",
    ]
    return "\n".join(lines)
