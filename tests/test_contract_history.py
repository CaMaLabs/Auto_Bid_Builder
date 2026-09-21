from auto_bid_builder.estimate.cost_detail import parse_cost_detail_text
from auto_bid_builder.validation.contract_history import (
    parse_change_order_text,
    reconcile_cost_detail_to_change_order,
)


def test_change_order_reconciles_to_cost_detail_scope_accounting():
    cost_text = """
JOB 5252 COST DETAIL JAN 01 2026 10:00:00 Page 1
Status Description Start Completion Terms Rep
JOB Synthetic Remodel RB
Item Qty Description
1 1 Base work.
E M P A F H S I Hours Each
0.0 0.0 0.0 0.0 0.0 0.0 0.0 8.0 8.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
1000.00 0.00 0.00 0.00 MO 0.00 1000.00 1000.00
Item Qty Description
2 1 CO1 Added slats.
E M P A F H S I Hours Each
0.0 0.0 0.0 0.0 0.0 0.0 0.0 2.0 2.0
0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0
100.00 100.00 100.00 100.00 100.00 100.00 100.00 125.00
Labor Materials Markup Add Code Tax Each Each Item Total
250.00 0.00 0.00 0.00 MO 0.00 250.00 250.00
Hours Actual Labor Materials Markup Add Tax Job Total
10.0 0.0 1250.00 0.00 0.00 0.00 0.00 1250.00
"""
    change_text = """
Synthetic Project
Subcontract Change Order No: 1 (FINAL)
Subcontract #: SP0001.002
SCO No. 1
PROJECT: Synthetic Project
SPG PCO # Description Amount
3 Added Slats
Proposal dated
$250.00
Original Subcontract Value: $1,000.00
Net Change by Previous Change Orders: $0.00
Amount of This Change Order (No. 1): $250.00
Current Adjusted Subcontract Value: $1,250.00
"""
    cost_detail = parse_cost_detail_text(cost_text)
    change_order = parse_change_order_text(change_text)
    assert change_order.subcontract_number == "SP0001.002"
    assert change_order.change_order_ref == "CO1"
    assert change_order.description == "Added Slats"
    assert change_order.original_contract_value == 1000.0
    assert change_order.change_order_amount == 250.0
    assert change_order.adjusted_contract_value == 1250.0

    result = reconcile_cost_detail_to_change_order(cost_detail, change_order)
    assert result["change_order_ref_matches"] is True
    assert result["base_contract_value_matches"] is True
    assert result["change_order_amount_matches"] is True
    assert result["adjusted_contract_value_matches"] is True
    assert result["all_available_checks_match"] is True
