from pathlib import Path
import zipfile

import fitz

from auto_bid_builder.bid_workspace import (
    add_documents,
    analyze_workspace,
    build_ai_review_package,
    create_workspace,
    load_manifest,
    workspace_status,
)


def _pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _docx(path: Path, text: str) -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml)


def _workspace(tmp_path: Path) -> Path:
    row = {
        "score": 55,
        "tier": "strong_review",
        "opportunity": {
            "title": "Test Retail Millwork",
            "bid_due_date": "2026-10-15",
            "source": "test",
        },
    }
    return create_workspace(tmp_path / "bids", row)


def test_guided_workspace_create_add_and_analyze(tmp_path: Path):
    root = _workspace(tmp_path)
    assert (root / "bid_docs").is_dir()
    assert load_manifest(root)["workflow"]["job_selected"] is True

    source = tmp_path / "A8.00.pdf"
    _pdf(source, "A8.00 ARCHITECTURAL MILLWORK CABINET CASEWORK BY OTHERS")
    copied = add_documents(root, [source])
    assert len(copied) == 1
    assert copied[0].exists()

    review = analyze_workspace(root)
    assert review["pdf_count"] == 1
    assert review["relevant_page_count"] >= 1
    status = workspace_status(root)
    assert status["analysis_status"] == "complete"
    assert Path(status["review_markdown"]).exists()


def test_incidental_counter_panel_language_is_not_priceable(tmp_path: Path):
    root = _workspace(tmp_path)
    source = tmp_path / "electrical.pdf"
    _pdf(source, "OVER-THE-COUNTER submittal. Electrical panelboard. Metal panel. Counter-sloping wires.")
    add_documents(root, [source])
    review = analyze_workspace(root)
    assert review["relevant_page_count"] == 0
    assert review["pages"] == []


def test_demolition_casework_is_review_only_not_new_scope(tmp_path: Path):
    root = _workspace(tmp_path)
    source = tmp_path / "A412.pdf"
    _pdf(source, "A412 ENLARGED RESTROOM PLAN. REMOVE EXISTING CASEWORK. Wood blocking at fixtures.")
    add_documents(root, [source])
    review = analyze_workspace(root)
    assert review["relevant_page_count"] == 0
    assert len(review["review_only"]) == 1
    assert "casework" in review["review_only"][0]["demolition_terms"]


def test_docx_addendum_is_reviewed(tmp_path: Path):
    root = _workspace(tmp_path)
    addendum = tmp_path / "Addendum_1.docx"
    _docx(addendum, "ADDENDUM NO. 1 revised bid form and project location")
    add_documents(root, [addendum])
    review = analyze_workspace(root)
    assert review["docx_count"] == 1
    assert workspace_status(root)["analysis_status"] == "complete"


def test_ai_review_package_contains_bid_docs_and_audit_outputs(tmp_path: Path):
    root = _workspace(tmp_path)
    source = tmp_path / "plans.pdf"
    _pdf(source, "ARCHITECTURAL MILLWORK CASEWORK")
    add_documents(root, [source])
    analyze_workspace(root)
    (root / "estimate" / "estimate_draft.json").write_text('{"project_title":"Synthetic"}', encoding="utf-8")
    (root / "output" / "jti_quote.pdf").write_bytes(b"synthetic quote")

    package = build_ai_review_package(root)
    assert package.exists()
    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())
    assert "AI_REVIEW_INSTRUCTIONS.txt" in names
    assert "bid_docs/plans.pdf" in names
    assert "estimate/estimate_draft.json" in names
    assert "output/bid_review.json" in names
    assert "output/jti_quote.pdf" in names
