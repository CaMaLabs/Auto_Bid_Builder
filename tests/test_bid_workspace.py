from pathlib import Path
import zipfile

import fitz

from auto_bid_builder.estimate.draft import (
    create_estimate_from_workspace,
    load_estimate,
    save_estimate,
)
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


def test_electrical_equipment_cabinets_and_panels_are_not_priceable(tmp_path: Path):
    root = _workspace(tmp_path)
    source = tmp_path / "electrical_equipment.pdf"
    _pdf(
        source,
        "BATTERY CHARGER control and monitoring panel. "
        "NEMA 250 Type 1 wall-mounted cabinet. "
        "SECTION 262716 ELECTRICAL CABINETS AND ENCLOSURES. "
        "Shop drawings for custom enclosures and cabinets. "
        "COMMUNICATIONS cabinets and terminal cabinets.",
    )
    add_documents(root, [source])
    review = analyze_workspace(root)
    assert review["relevant_page_count"] == 0
    assert review["pages"] == []


def test_architectural_cabinets_still_price_with_material_context(tmp_path: Path):
    root = _workspace(tmp_path)
    source = tmp_path / "A8.10.pdf"
    _pdf(
        source,
        "A8.10 ARCHITECTURAL MILLWORK. Provide wood veneer base cabinets, "
        "plastic laminate upper cabinets, casework and solid-surface countertops.",
    )
    add_documents(root, [source])
    review = analyze_workspace(root)
    assert review["relevant_page_count"] == 1
    terms = set(review["pages"][0]["scope_terms"])
    assert "millwork" in terms
    assert "cabinetry" in terms


def test_reanalysis_replaces_stale_unreviewed_auto_estimate(tmp_path: Path):
    root = _workspace(tmp_path)

    # Simulate an estimate created by the older, over-broad detector.
    old_review = {
        "pages": [
            {
                "source": "electrical.pdf",
                "page": 1,
                "sheet": None,
                "relevance_score": 12,
                "scope_terms": ["cabinetry", "panel"],
                "signals": [],
            }
        ]
    }
    (root / "output" / "bid_review.json").write_text(
        __import__("json").dumps(old_review),
        encoding="utf-8",
    )
    draft = create_estimate_from_workspace(root)
    assert len(draft.lines) == 2
    assert all("AUTO-SCOPE:" in line.estimator_note for line in draft.lines)
    # Even a previously confirmed quote must be rebuilt if its scope is still
    # entirely machine-generated and has no manual-edit marker.
    draft.scope_review_confirmed = True
    draft.pricing_profile_confirmed = True
    draft.tax_rate_confirmed = True
    save_estimate(root, draft)

    # Stale quote files must not survive the corrected analysis.
    for name in ("jti_quote.pdf", "jti_quote.html", "quote_preview.pdf", "quote_preview.html"):
        (root / "output" / name).write_bytes(b"stale")

    source = tmp_path / "electrical.pdf"
    _pdf(
        source,
        "SECTION 262716 ELECTRICAL CABINETS AND ENCLOSURES. "
        "NEMA 250 wall-mounted cabinet and control panel.",
    )
    add_documents(root, [source])

    review = analyze_workspace(root)

    assert review["relevant_page_count"] == 0
    assert review["estimate_refresh"]["status"] == "rebuilt_auto_generated"
    assert review["estimate_refresh"]["line_count"] == 0
    refreshed = load_estimate(root)
    assert refreshed is not None
    assert refreshed.lines == []
    assert not (root / "output" / "jti_quote.pdf").exists()
    assert not (root / "output" / "quote_preview.pdf").exists()


def test_reanalysis_preserves_manual_estimate_but_marks_it_stale(tmp_path: Path):
    root = _workspace(tmp_path)
    old_review = {
        "pages": [
            {
                "source": "plans.pdf",
                "page": 1,
                "sheet": "A8.10",
                "relevance_score": 12,
                "scope_terms": ["millwork"],
                "signals": [],
            }
        ]
    }
    (root / "output" / "bid_review.json").write_text(
        __import__("json").dumps(old_review),
        encoding="utf-8",
    )
    draft = create_estimate_from_workspace(root)
    draft.lines[0].description = "Estimator-entered custom scope"
    draft.lines[0].estimator_note = "MANUAL: estimator adjusted this line."
    draft.scope_review_confirmed = True
    draft.pricing_profile_confirmed = True
    draft.tax_rate_confirmed = True
    save_estimate(root, draft)

    source = tmp_path / "electrical.pdf"
    _pdf(source, "ELECTRICAL CABINETS AND ENCLOSURES. NEMA control panel.")
    add_documents(root, [source])
    review = analyze_workspace(root)

    assert review["estimate_refresh"]["status"] == "manual_estimate_preserved_stale"
    refreshed = load_estimate(root)
    assert refreshed is not None
    assert refreshed.lines[0].description == "Estimator-entered custom scope"
    assert refreshed.scope_review_confirmed is False
    assert refreshed.pricing_profile_confirmed is False
    assert refreshed.tax_rate_confirmed is False
    assert "STALE-SCOPE:" in refreshed.general_notes
