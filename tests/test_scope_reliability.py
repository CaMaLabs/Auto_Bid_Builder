from pathlib import Path

import fitz
import pytest

from auto_bid_builder.analysis.scope import scan_text
from auto_bid_builder.bid_workspace import (
    add_documents,
    analyze_workspace,
    create_workspace,
)
from auto_bid_builder.estimate.draft import EstimateDraft, EstimateLine
from auto_bid_builder.quote.jti_render import write_jti_quote
from auto_bid_builder.validation.project_identity import check_workspace_project_identity


def _pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(36, 36, 550, 650), text, fontsize=10)
    document.save(path)
    document.close()


@pytest.mark.parametrize("snippet", [
    'APPENDIX "C"\nSection 01 45 33.3\nCHANGE ROOM YES NO COMMENTS\n'
    'Hangers/lockers/bins for street clothes? _____ _____',
    'SECTION 28 13 00\nACCESS CONTROL\n'
    'Storage Cabinet: Locking cabinet with three adjustable shelves and '
    'racks for disks, tapes, and printer paper.\nACCESS CONTROL\n28 13 00 - 37',
    'SECTION 27 11 00\nCOMMUNICATIONS EQUIPMENT ROOM FITTINGS\n'
    'Backboards: plywood, fire-retardant treated.\n'
    'Modular wall cabinets: steel or aluminum construction, louvered side panels.\n'
    '27 11 00 - 2',
    'SECTION 08 71 11 DOOR HARDWARE\n'
    'KEY CONTROL SYSTEM\nProvide standard metal cabinet and hinged-panel '
    'cabinet for wall mounting.\nDOOR HARDWARE',
    'SECTION 22 05 00\nProvide escutcheons at pipe penetrations within '
    'cabinets and millwork.\n22 05 00 - 5',
    'ARCHITECTURAL ABBREVIATIONS\nCABINET\nCOUNTERTOP\nWOOD VENEER\n'
    'ELECTRICAL PANEL\nDRAWING ABBREVIATIONS',
    'RESTROOM FINISHES LEGEND: WV WOOD VENEER, WD SOLID WOOD, '
    'CT CERAMIC TILE. Materials noted for legend only.',
    'GENERAL NOTE: FOR TYPICAL BACKING/BLOCKING AT VARIOUS FIXTURES, '
    'ACCESSORIES, EQUIPMENT, CASEWORK ETC. SEE DETAIL 15/A502.',
    'SECTION 27 15 00\nEach terminal strip in each cabinet, rack or panel '
    'shall be labeled. Communications horizontal cabling.\n27 15 00 - 10',
])
def test_other_trades_checklists_and_legends_not_auto_priceable(snippet: str):
    row = scan_text(snippet, source="manual.pdf")
    assert row is None or not row.scope_terms


@pytest.mark.parametrize("snippet, expected", [
    ("A8.10 ARCHITECTURAL MILLWORK. Furnish custom wood veneer cabinets "
     "and solid-surface countertops.", "millwork"),
    ("SECTION 06 41 00 ARCHITECTURAL WOOD CASEWORK\n"
     "Provide plywood casework for reception and base cabinets.", "casework"),
    ("A8.20 Provide custom architectural wood shelving with laminate finish.", "shelving"),
])
def test_real_architectural_scope_remains_detectable(snippet: str, expected: str):
    row = scan_text(snippet, source="A8.10.pdf", sheet="A8.10")
    assert row is not None
    assert expected in row.scope_terms


def test_10300_opportunity_rejects_9552_source_documents(tmp_path: Path):
    workspace = create_workspace(tmp_path / "bids", {
        "opportunity": {
            "title": "10300 - Playground Structure and Restroom Upgrade",
            "external_id": "0000034413",
            "source": "California DGS RESD",
        }
    })
    doc = tmp_path / "9552_-_Project_Manual.pdf"
    _pdf(doc, "PROJECT MANUAL\nOSP SECURITY UPGRADES\n"
              "PROJECT NUMBER: 9552\nWEST SACRAMENTO")
    add_documents(workspace, [doc])

    check = check_workspace_project_identity(workspace)
    assert check["status"] == "conflict"
    assert check["expected"] == "10300"
    assert check["document_ids"] == ["9552"]

    review = analyze_workspace(workspace)
    assert review["project_identity"]["status"] == "conflict"
    with pytest.raises(ValueError, match="project identity mismatch"):
        write_jti_quote(
            workspace,
            EstimateDraft(
                project_title="Wrong project",
                pricing_profile_confirmed=True,
                tax_rate_confirmed=True,
                scope_review_confirmed=True,
                lines=[EstimateLine(item=1, description="Cabinet", manual_add=1000)],
            ),
        )
    assert not (workspace / "output" / "jti_quote.pdf").exists()


def test_matching_9552_project_is_not_blocked(tmp_path: Path):
    workspace = create_workspace(tmp_path / "bids", {
        "opportunity": {"title": "9552 - OSP Security Upgrades", "source": "DGS"}
    })
    pdf = tmp_path / "Project_9552_Drawings.pdf"
    _pdf(pdf, "OSP SECURITY UPGRADES\nPROJECT NUMBER: 9552")
    add_documents(workspace, [pdf])
    check = check_workspace_project_identity(workspace)
    assert check["status"] == "verified"
    assert check["errors"] == []
