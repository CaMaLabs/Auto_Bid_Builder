"""Cross-check an opportunity against project numbers actually printed on bid files.

Only high-confidence document signals are used. Unknown project IDs are not
treated as mismatches. A known mismatch is a hard block on quote generation.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

import fitz


_PROJECT_ID = re.compile(r"(?<!\d)(?!19\d\d\b|20\d\d\b)(\d{4,6})(?!\d)")
_EXPLICIT_NUMBER = re.compile(
    r"\bproject\s*(?:number|no\.?|#)\s*[:#\s]*([0-9]{4,6})\b", re.I
)
_FILENAME_NUMBER = re.compile(
    r"(?:^|[_\s-])([0-9]{4,6})(?=[_.\s-]|$)", re.I
)
_TITLE_NUMBER = re.compile(
    r"^\s*(?:project\s*)?([0-9]{4,6})\s*[-:–]\s*", re.I
)


def _valid_id(value: str) -> str | None:
    text = str(value or "").strip()
    if not text or not _PROJECT_ID.fullmatch(text):
        return None
    return str(int(text))


def _opportunity_id(opportunity: dict) -> str | None:
    metadata = opportunity.get("metadata") if isinstance(opportunity.get("metadata"), dict) else {}
    for value in (metadata.get("project_number"), metadata.get("project_id")):
        if candidate := _valid_id(str(value or "")):
            return candidate
    title = str(opportunity.get("title") or "")
    matched = _TITLE_NUMBER.search(title)
    if matched:
        return _valid_id(matched.group(1))
    source = str(opportunity.get("source") or "").lower()
    # A source's notice ID is often NOT the construction project number; only
    # trust a short numeric ID for project-level DGS/Cal eProcure opportunities.
    if any(part in source for part in ("caleprocure", "dgs", "california")):
        return _valid_id(str(opportunity.get("external_id") or ""))
    return None


def _pdf_project_id(path: Path) -> tuple[str | None, str]:
    # The first pages contain the cover and project title page. A matching
    # named project-number field is stronger evidence than an arbitrary digit.
    try:
        with fitz.open(path) as doc:
            for page in range(min(3, doc.page_count)):
                text = doc[page].get_text("text") or ""
                matched = _EXPLICIT_NUMBER.search(text)
                if matched and (value := _valid_id(matched.group(1))):
                    return value, f"{path.name}, PDF page {page + 1}: explicit project number"
    except Exception:
        return None, ""
    match = _FILENAME_NUMBER.search(path.stem)
    if match and (value := _valid_id(match.group(1))):
        return value, f"{path.name}: filename project number"
    return None, ""


def check_workspace_project_identity(root: str | Path) -> dict:
    root = Path(root)
    manifest_path = root / "bid_workspace.json"
    if not manifest_path.exists():
        return {"status": "unknown", "expected": None, "document_ids": [], "evidence": [], "errors": []}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = manifest.get("opportunity") or {}
    opportunity = row.get("opportunity", row) if isinstance(row, dict) else {}
    if not isinstance(opportunity, dict):
        opportunity = {}
    expected = _opportunity_id(opportunity)

    observed: list[tuple[str, str]] = []
    files = sorted((root / "bid_docs").rglob("*.pdf"))
    for path in files:
        if value := _pdf_project_id(path):
            found_id, evidence = value
            if found_id:
                observed.append((found_id, evidence))

    counts = Counter(value for value, _ in observed)
    document_ids = sorted(counts)
    evidence = [detail for _, detail in observed]
    errors: list[str] = []
    if len(document_ids) > 1:
        errors.append("Bid documents identify multiple different project numbers: " + ", ".join(document_ids))
    if expected is not None and document_ids and any(pid != expected for pid in document_ids):
        errors.append(
            f"Workspace opportunity identifies Project {expected}, but the uploaded PDFs identify "
            + ", ".join(f"Project {pid}" for pid in document_ids)
            + ". These may belong to different jobs."
        )
    return {
        "status": "conflict" if errors else ("verified" if expected and document_ids else "unknown"),
        "expected": expected,
        "document_ids": document_ids,
        "evidence": evidence,
        "errors": errors,
    }
