from pathlib import Path

import fitz

from auto_bid_builder.bid_workspace import add_documents, analyze_workspace, create_workspace, load_manifest, workspace_status


def _pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_guided_workspace_create_add_and_analyze(tmp_path: Path):
    row = {
        "score": 55,
        "tier": "strong_review",
        "opportunity": {
            "title": "Test Retail Millwork",
            "bid_due_date": "2026-10-15",
            "source": "test",
        },
    }
    root = create_workspace(tmp_path / "bids", row)
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
