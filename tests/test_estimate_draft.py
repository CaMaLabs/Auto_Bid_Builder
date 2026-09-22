from pathlib import Path
import json

from auto_bid_builder.estimate.draft import (
    EstimateDraft,
    EstimateLine,
    create_estimate_from_workspace,
    load_estimate,
    save_estimate,
    write_quote_preview,
)


def test_jti_style_line_math_and_review_gates(tmp_path: Path):
    line = EstimateLine(
        item=1,
        description="Cafe cabinetry",
        quantity=2,
        labor_hours={"F": 10, "I": 4},
        material_cost=1000,
        material_markup_rate=0.60,
        material_tax_rate=0.0838,
        manual_add=100,
    )
    draft = EstimateDraft(
        project_title="Test",
        labor_rates={"E": 100, "M": 100, "P": 100, "A": 100, "F": 100, "H": 100, "S": 100, "I": 150},
        lines=[line],
    )
    assert line.labor_total(draft.labor_rates) == 1600
    assert line.material_markup == 600
    assert line.material_tax == 83.8
    assert line.pretax_total(draft.labor_rates) == 3300
    assert line.quote_each(draft.labor_rates) == 1650
    assert line.tax_each == 41.9
    assert draft.total == 3383.8
    assert draft.ready_for_quote is False

    draft.scope_review_confirmed = True
    draft.pricing_profile_confirmed = True
    draft.tax_rate_confirmed = True
    assert draft.warnings() == []
    assert draft.ready_for_quote is True


def test_workspace_review_seeds_scope_lines_and_persists(tmp_path: Path):
    root = tmp_path / "bid"
    (root / "output").mkdir(parents=True)
    (root / "estimate").mkdir()
    (root / "bid_workspace.json").write_text(
        json.dumps({"opportunity": {"opportunity": {"title": "Retail TI"}}}), encoding="utf-8"
    )
    (root / "output" / "bid_review.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"source": "plans.pdf", "page": 10, "sheet": "A8.00", "relevance_score": 15, "scope_terms": ["millwork", "cabinet"]},
                    {"source": "plans.pdf", "page": 11, "sheet": "A8.00", "relevance_score": 12, "scope_terms": ["shelving"]},
                    {"source": "plans.pdf", "page": 20, "sheet": "A9.00", "relevance_score": 8, "scope_terms": ["wood veneer"]},
                ]
            }
        ),
        encoding="utf-8",
    )

    draft = create_estimate_from_workspace(root)
    assert draft.project_title == "Retail TI"
    assert len(draft.lines) == 2
    assert "A8.00" in draft.lines[0].description
    assert "millwork" in draft.lines[0].description
    assert load_estimate(root) is not None

    draft.lines[0].manual_add = 500
    save_estimate(root, draft)
    loaded = load_estimate(root)
    assert loaded is not None
    assert loaded.lines[0].manual_add == 500


def test_quote_preview_files_are_created(tmp_path: Path):
    root = tmp_path / "bid"
    (root / "output").mkdir(parents=True)
    draft = EstimateDraft(
        project_title="Preview Test",
        pricing_profile_confirmed=True,
        tax_rate_confirmed=True,
        scope_review_confirmed=True,
        lines=[EstimateLine(item=1, description="Millwork", manual_add=1250)],
    )
    html_path, pdf_path = write_quote_preview(root, draft)
    assert html_path.exists()
    assert pdf_path.exists()
    assert "Preview Test" in html_path.read_text(encoding="utf-8")
    assert pdf_path.stat().st_size > 500
