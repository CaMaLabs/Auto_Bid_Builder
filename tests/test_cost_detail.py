from auto_bid_builder.estimate.cost_detail import parse_cost_detail_text


def test_cost_detail_reconstructs_pricing_without_hardcoded_rates():
    text = """
JOB 4242 COST DETAIL JAN 01 2026 10:00:00 Page 1
Status Description Start Completion Terms Rep
JOB Synthetic Millwork 25/25/25/25 AB
Item Qty Description
1 2 Fabricate and install synthetic cabinet.
E M P A F H S I Hours Each
1.0 2.0 0.0 0.0 0.0 0.0 0.0 1.0 4.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
50.00 50.00 50.00 50.00 50.00 50.00 50.00 100.00
Labor Materials Markup Add Code Tax Each Each Item Total
250.00 200.00 100.00 10.00 MO 20.00 580.00 1160.00
JOB 4242 COST DETAIL JAN 01 2026 10:00:00 Page 2
Hours Actual Labor Materials Markup Add Tax Job Total
8.0 0.0 500.00 400.00 200.00 20.00 40.00 1160.00
General Notes
"""
    doc = parse_cost_detail_text(text)
    assert doc.job_number == "4242"
    assert doc.job_name == "Synthetic Millwork"
    assert doc.terms == "25/25/25/25"
    assert len(doc.lines) == 1
    line = doc.lines[0]
    assert line.calculated_labor_each == 250.0
    assert line.calculated_sell_each == 580.0
    assert line.calculated_item_total == 1160.0
    assert line.markup_rate_on_materials == 0.5
    assert line.tax_rate_on_materials == 0.1
    assert line.inclusion_status == "base"
    assert doc.inferred_labor_rates["E"] == 50.0
    assert doc.inferred_labor_rates["I"] == 100.0
    assert doc.inferred_material_markup_rate == 0.5
    assert doc.inferred_material_tax_rate == 0.1
    assert doc.to_dict()["totals_match_display"] is True


def test_cost_detail_classifies_zero_quantity_options_selected_alternates_and_change_orders():
    text = """
JOB 5252 COST DETAIL JAN 01 2026 10:00:00 Page 1
Status Description Start Completion Terms Rep
JOB Synthetic Remodel RB
Item Qty Description
1 1 Base cabinet.
E M P A F H S I Hours Each
0.0 1.0 0.0 0.0 0.0 0.0 0.0 1.0 2.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
225.00 100.00 60.00 0.00 MO 10.00 395.00 395.00
Item Qty Description
2 0 (Removed from Scope) Wall display.
E M P A F H S I Hours Each
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
0.00 0.00 0.00 500.00 MO 0.00 500.00 0.00
Item Qty Description
3 1 Alternate Add: selected premium finish.
E M P A F H S I Hours Each
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
0.00 0.00 0.00 100.00 MO 0.00 100.00 100.00
Item Qty Description
4 1 CO1 Furnish and install added slats.
E M P A F H S I Hours Each
0.0 0.0 0.0 0.0 0.0 0.0 0.0 4.0 4.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
500.00 100.00 60.00 30.00 MO 10.00 700.00 700.00
Hours Actual Labor Materials Markup Add Tax Job Total
6.0 0.0 725.00 200.00 120.00 130.00 20.00 1195.00
General Notes
"""
    doc = parse_cost_detail_text(text)
    assert doc.job_name == "Synthetic Remodel"
    assert doc.terms is None
    assert doc.rep == "RB"
    assert [line.inclusion_status for line in doc.lines] == [
        "base",
        "removed",
        "alternate_selected",
        "change_order",
    ]
    assert doc.lines[-1].change_order_ref == "CO1"
    assert doc.change_order_total == 700.0
    assert doc.selected_alternate_total == 100.0
    assert doc.inferred_base_contract_total == 495.0
    assert doc.to_dict()["totals_match_display"] is True
