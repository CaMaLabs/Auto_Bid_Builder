from pathlib import Path

from auto_bid_builder.estimate.draft import EstimateDraft, EstimateLine
from auto_bid_builder.quote.jti_render import write_jti_quote


def test_jti_quote_uses_familiar_customer_columns(tmp_path: Path):
    draft = EstimateDraft(
        project_title="Synthetic Retail TI",
        quote_number="123456",
        quote_date="2026-09-22",
        terms="30/30/30/10",
        rep="CL",
        general_notes="Synthetic note only.",
        labor_rates={"E": 100, "M": 100, "P": 100, "A": 100, "F": 100, "H": 100, "S": 100, "I": 125},
        pricing_profile_confirmed=True,
        tax_rate_confirmed=True,
        scope_review_confirmed=True,
        lines=[
            EstimateLine(
                item=1,
                description="Custom millwork fixture",
                labor_hours={"M": 2, "I": 1},
                material_cost=500,
                material_markup_rate=0.60,
                material_tax_rate=0.0838,
                estimator_note="Internal confidence note should not appear on quote",
                source_refs=["plans.pdf / A8.00"],
            )
        ],
    )
    html_path, pdf_path = write_jti_quote(tmp_path, draft)
    html = html_path.read_text(encoding="utf-8")
    for heading in ("Item", "Description", "Qty", "Each", "Code", "Tax Each", "Amount", "Quote Total"):
        assert heading in html
    assert "JEFFREY TROTT INDUSTRIES" in html
    assert "Internal confidence note" not in html
    assert "plans.pdf / A8.00" not in html
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 500
