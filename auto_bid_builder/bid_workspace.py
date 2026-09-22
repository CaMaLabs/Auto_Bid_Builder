from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Iterable
import xml.etree.ElementTree as ET
import zipfile

from .analysis.scope import scan_pdf, scan_text


MANIFEST_NAME = "bid_workspace.json"
ANALYSIS_NAME = "bid_review.json"
ANALYSIS_MARKDOWN_NAME = "bid_review.md"
AI_REVIEW_PACKAGE_NAME = "AI_review_package.zip"
WORKSPACE_DIRS = ("bid_docs", "takeoff", "estimate", "output")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_workspace_root() -> Path:
    documents = Path.home() / "Documents"
    return documents / "JTI Bids"


def _safe_name(value: str, fallback: str = "New Bid") -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", value or "")
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:90].strip()
    return value or fallback


def _unique_workspace_path(base_root: Path, desired_name: str) -> Path:
    candidate = base_root / desired_name
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = base_root / f"{desired_name} ({index})"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Unable to choose a unique bid folder name.")


def create_workspace(base_root: str | Path, opportunity_row: dict) -> Path:
    base_root = Path(base_root).expanduser()
    base_root.mkdir(parents=True, exist_ok=True)
    opportunity = opportunity_row.get("opportunity", opportunity_row)
    title = _safe_name(str(opportunity.get("title") or "New Bid"))
    due = str(opportunity.get("bid_due_date") or "").strip()
    suffix = ""
    if due:
        compact_due = re.sub(r"[^0-9A-Za-z-]", "-", due).strip("-")
        suffix = f" - due {compact_due}" if compact_due else ""
    root = _unique_workspace_path(base_root, _safe_name(title + suffix))
    root.mkdir(parents=True)
    for directory in WORKSPACE_DIRS:
        (root / directory).mkdir(exist_ok=True)
    manifest = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "opportunity": opportunity_row,
        "documents": [],
        "analysis": {
            "status": "not_run",
            "last_run_at": None,
            "pdf_count": 0,
            "docx_count": 0,
            "relevant_page_count": 0,
        },
        "workflow": {
            "job_selected": True,
            "documents_added": False,
            "documents_reviewed": False,
            "scope_review_complete": False,
            "estimate_review_complete": False,
            "quote_ready": False,
        },
    }
    save_manifest(root, manifest)
    (root / "opportunity.json").write_text(json.dumps(opportunity_row, indent=2), encoding="utf-8")
    return root


def load_manifest(root: str | Path) -> dict:
    path = Path(root) / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(f"This folder is not an Auto Bid Builder workspace: {path.parent}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(root: str | Path, manifest: dict) -> Path:
    path = Path(root) / MANIFEST_NAME
    manifest["updated_at"] = _utc_now()
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _extract_bid_zip(archive: Path, destination: Path) -> list[Path]:
    extracted_root = destination / f"{archive.stem}_extracted"
    extracted_root.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    root_resolved = extracted_root.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            relative = Path(info.filename.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts:
                continue
            target = extracted_root / relative
            try:
                target.resolve().relative_to(root_resolved)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def add_documents(root: str | Path, sources: Iterable[str | Path]) -> list[Path]:
    root = Path(root)
    manifest = load_manifest(root)
    destination = root / "bid_docs"
    destination.mkdir(exist_ok=True)
    added: list[Path] = []
    known = {str(item.get("stored_name", "")).lower() for item in manifest.get("documents", [])}
    for source_value in sources:
        source = Path(source_value)
        if not source.is_file():
            continue
        target = destination / source.name
        if target.resolve() == source.resolve():
            added.append(target)
        else:
            if target.exists():
                stem, suffix = target.stem, target.suffix
                index = 2
                while target.exists():
                    target = destination / f"{stem} ({index}){suffix}"
                    index += 1
            shutil.copy2(source, target)
            added.append(target)
        record = None
        if target.name.lower() not in known:
            record = {
                "original_name": source.name,
                "stored_name": target.name,
                "added_at": _utc_now(),
                "kind": target.suffix.lower().lstrip(".") or "file",
            }
            manifest.setdefault("documents", []).append(record)
            known.add(target.name.lower())
        if target.suffix.lower() == ".zip":
            try:
                extracted = _extract_bid_zip(target, destination)
            except zipfile.BadZipFile:
                extracted = []
                if record is not None:
                    record["extraction_error"] = "The ZIP file could not be opened."
            else:
                added.extend(extracted)
                if record is not None:
                    record["extracted_count"] = len(extracted)
                    record["extracted_folder"] = f"{target.stem}_extracted"
    if added:
        manifest.setdefault("workflow", {})["documents_added"] = True
        manifest.setdefault("analysis", {})["status"] = "needs_run"
        save_manifest(root, manifest)
    return added


def _docx_text(path: Path) -> str:
    """Extract paragraph/table text from DOCX without requiring python-docx."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    chunks: list[str] = []
    for element in root.iter():
        if element.tag.endswith("}t") and element.text:
            chunks.append(element.text)
        elif element.tag.endswith("}p"):
            chunks.append("\n")
    return " ".join(chunks).replace(" \n ", "\n")


def _review_markdown(root: Path, payload: dict) -> str:
    manifest = load_manifest(root)
    opportunity = manifest.get("opportunity", {}).get("opportunity", manifest.get("opportunity", {}))
    title = opportunity.get("title") or root.name
    lines = [
        f"# Bid document review - {title}",
        "",
        "This is an estimator review aid, not a final scope decision. Every item below comes from the current files in `bid_docs`.",
        "",
        f"PDF files reviewed: {payload.get('pdf_count', 0)}",
        f"DOCX files reviewed: {payload.get('docx_count', 0)}",
        f"Scope/review evidence rows found: {payload.get('relevant_page_count', 0)}",
        "",
    ]
    errors = payload.get("errors", [])
    if errors:
        lines.extend(["## Files that need attention", ""])
        for error in errors:
            lines.append(f"- {error['file']}: {error['error']}")
        lines.append("")
    lines.extend(["## Highest-priority evidence", ""])
    for row in payload.get("pages", [])[:40]:
        sheet = f" / sheet {row.get('sheet')}" if row.get("sheet") else ""
        positive = list(row.get("scope_terms") or [])
        demolition = list(row.get("demolition_terms") or [])
        adjacent = list(row.get("adjacent_review_terms") or [])
        if positive:
            label = "potential new scope: " + ", ".join(positive)
        elif demolition:
            label = "demolition/existing only: " + ", ".join(demolition)
        elif adjacent:
            label = "adjacent JTI review: " + ", ".join(adjacent)
        else:
            label = "responsibility language requiring review"
        lines.append(f"- **{row.get('source')} - page {row.get('page')}{sheet}** - score {row.get('relevance_score')} - {label}")
        by_others = row.get("by_others_mentions") or []
        if by_others:
            lines.append(f"  - Responsibility/exclusion language: {', '.join(by_others)}")
    if not payload.get("pages"):
        lines.append("- No high-confidence JTI scope language was detected. Do not create a fabrication price from incidental terminology alone.")
    lines.extend([
        "",
        "## Next estimator action",
        "",
        "Review positive scope separately from demolition/existing references and adjacent-trade items. Check responsibility schedules, finish schedules, elevations/details, specifications, and addenda before accepting scope or pricing assumptions.",
        "",
    ])
    return "\n".join(lines)


def analyze_workspace(root: str | Path) -> dict:
    root = Path(root)
    manifest = load_manifest(root)
    pdfs = sorted((root / "bid_docs").glob("**/*.pdf"))
    docx_files = sorted((root / "bid_docs").glob("**/*.docx"))
    pages: list[dict] = []
    errors: list[dict[str, str]] = []
    for pdf in pdfs:
        try:
            pages.extend(asdict(row) for row in scan_pdf(pdf))
        except Exception as exc:
            errors.append({"file": str(pdf.relative_to(root / "bid_docs")), "error": f"{type(exc).__name__}: {exc}"})
    for docx in docx_files:
        try:
            row = scan_text(_docx_text(docx), source=docx.name)
            if row is not None:
                pages.append(asdict(row))
        except Exception as exc:
            errors.append({"file": str(docx.relative_to(root / "bid_docs")), "error": f"{type(exc).__name__}: {exc}"})
    pages.sort(key=lambda row: (-int(row.get("relevance_score", 0)), row.get("source", ""), int(row.get("page", 0))))
    payload = {
        "generated_at": _utc_now(),
        "pdf_count": len(pdfs),
        "docx_count": len(docx_files),
        "relevant_page_count": len(pages),
        "errors": errors,
        "pages": pages,
    }
    (root / "output" / ANALYSIS_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (root / "output" / ANALYSIS_MARKDOWN_NAME).write_text(_review_markdown(root, payload), encoding="utf-8")
    analysis = manifest.setdefault("analysis", {})
    reviewed_count = len(pdfs) + len(docx_files)
    analysis.update({
        "status": "complete" if reviewed_count and not errors else ("partial" if reviewed_count else "no_supported_docs"),
        "last_run_at": payload["generated_at"],
        "pdf_count": len(pdfs),
        "docx_count": len(docx_files),
        "relevant_page_count": len(pages),
        "error_count": len(errors),
    })
    workflow = manifest.setdefault("workflow", {})
    workflow["documents_added"] = bool(manifest.get("documents")) or bool(reviewed_count)
    workflow["documents_reviewed"] = bool(reviewed_count)
    save_manifest(root, manifest)
    return payload


def build_ai_review_package(root: str | Path) -> Path:
    """Create a local ZIP containing the current bid plus its supporting evidence.

    The package is intentionally created inside the private bid workspace. Nothing is
    uploaded or committed. A human can attach the ZIP to an AI review conversation.
    """
    root = Path(root)
    if not (root / MANIFEST_NAME).exists():
        raise FileNotFoundError("Not an Auto Bid Builder workspace.")
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    target = output / AI_REVIEW_PACKAGE_NAME
    readme = (
        "JTI AUTO BID BUILDER - AI DOUBLE-CHECK PACKAGE\n\n"
        "Review the proposed bid against every supporting document. Check for omitted scope, "
        "false-positive scope, demolition mistaken for new fabrication, by-others/NIC language, "
        "addenda, quantities, finishes, material assumptions, labor assumptions, tax, exclusions, "
        "and contradictions between drawings/specifications. Do not assume the generated estimate "
        "is correct. Cite the source document/page for every recommended change.\n"
    )
    include_roots = [root / "bid_docs", root / "takeoff", root / "estimate"]
    include_files = [
        root / MANIFEST_NAME,
        root / "opportunity.json",
        output / ANALYSIS_NAME,
        output / ANALYSIS_MARKDOWN_NAME,
        output / "quote_preview.pdf",
        output / "quote_preview.html",
    ]
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("AI_REVIEW_INSTRUCTIONS.txt", readme)
        for file in include_files:
            if file.is_file():
                archive.write(file, file.relative_to(root).as_posix())
        for folder in include_roots:
            if not folder.exists():
                continue
            for file in sorted(folder.rglob("*")):
                if file.is_file():
                    archive.write(file, file.relative_to(root).as_posix())
    return target


def workspace_status(root: str | Path) -> dict:
    root = Path(root)
    manifest = load_manifest(root)
    bid_docs = root / "bid_docs"
    files = [p for p in bid_docs.glob("**/*") if p.is_file()]
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    docx_files = [p for p in files if p.suffix.lower() == ".docx"]
    analysis = manifest.get("analysis", {})
    workflow = manifest.get("workflow", {})
    return {
        "root": str(root),
        "title": manifest.get("opportunity", {}).get("opportunity", manifest.get("opportunity", {})).get("title") or root.name,
        "file_count": len(files),
        "pdf_count": len(pdfs),
        "docx_count": len(docx_files),
        "analysis_status": analysis.get("status", "not_run"),
        "relevant_page_count": int(analysis.get("relevant_page_count", 0) or 0),
        "workflow": workflow,
        "review_json": str(root / "output" / ANALYSIS_NAME),
        "review_markdown": str(root / "output" / ANALYSIS_MARKDOWN_NAME),
        "ai_review_package": str(root / "output" / AI_REVIEW_PACKAGE_NAME),
    }
