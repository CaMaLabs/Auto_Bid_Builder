from pathlib import Path
import json

from auto_bid_builder.estimate.autoprice import apply_auto_pricing
from auto_bid_builder.estimate.draft import EstimateDraft, EstimateLine


def test_best_effort_fills_zero_dollar_scope_and_requires_review(tmp_path: Path):
    draft = EstimateDraft(
        project_title="Synthetic Bid",
        labor_rates={"E": 100, "M": 100, "P": 100, "A": 100, "F": 100, "H": 100, "S": 100, "I": 125},
        pricing_profile_confirmed=True,
        tax_rate_confirmed=True,
        lines=[
            EstimateLine(item=1, description="Custom casework cabinetry", source_refs=["plans.pdf / A8.00"]),
        ],
    )
    summary = apply_auto_pricing(draft, calibration_dir=tmp_path, collapse_generated=False)
    assert summary.filled_lines == 1
    assert summary.heuristic_lines == 1
    assert draft.lines[0].material_cost > 0
    assert sum(draft.lines[0].normalized_hours().values()) > 0
    assert draft.lines[0].material_markup_rate == 0.60
    assert "AUTO-PRICED" in draft.lines[0].estimator_note
    assert draft.pricing_profile_confirmed is False
    assert draft.tax_rate_confirmed is False


def test_local_history_is_preferred_over_fallback(tmp_path: Path):
    payload = {
        "lines": [
            {
                "quantity": 1,
                "description": "Custom reception casework cabinet with laminate finish",
                "projected_hours": {"E": 0, "M": 4, "P": 0, "A": 3, "F": 1, "H": 0, "S": 0, "I": 2},
                "materials_each": 1200,
                "markup_each": 720,
                "add_each": 50,
                "tax_each": 100.56,
                "code": "MILL",
                "markup_rate_on_materials": 0.60,
                "tax_rate_on_materials": 0.0838,
                "inclusion_status": "base"
            }
        ]
    }
    (tmp_path / "synthetic.json").write_text(json.dumps(payload), encoding="utf-8")
    draft = EstimateDraft(
        project_title="Synthetic Bid",
        labor_rates={"E": 100, "M": 100, "P": 100, "A": 100, "F": 100, "H": 100, "S": 100, "I": 125},
        lines=[EstimateLine(item=1, description="Reception casework cabinet")],
    )
    summary = apply_auto_pricing(draft, calibration_dir=tmp_path, collapse_generated=False)
    line = draft.lines[0]
    assert summary.historical_lines == 1
    assert summary.heuristic_lines == 0
    assert line.material_cost == 1200
    assert line.material_markup_rate == 0.60
    assert round(line.material_tax_rate, 4) == 0.0838
    assert line.labor_hours["M"] == 4


def test_page_review_rows_collapse_before_pricing(tmp_path: Path):
    draft = EstimateDraft(
        project_title="Synthetic",
        lines=[
            EstimateLine(item=1, description="Review scope in plans.pdf page 1 — detected cabinet.", source_refs=["p1"]),
            EstimateLine(item=2, description="Review scope in plans.pdf page 2 — detected cabinetry.", source_refs=["p2"]),
            EstimateLine(item=3, description="Review scope in plans.pdf page 3 — detected panel, veneer.", source_refs=["p3"]),
        ],
    )
    summary = apply_auto_pricing(draft, calibration_dir=tmp_path, collapse_generated=True)
    assert summary.collapsed_lines >= 1
    assert len(draft.lines) < 3
    assert all(line.material_cost > 0 for line in draft.lines)
