from auto_bid_builder.procurement import PurchaseEvidence, summarize_procurement


def test_procurement_summary_uses_document_total_once_and_keeps_unpriced_evidence():
    rows = (
        PurchaseEvidence(
            source="vendor_a_order.pdf",
            vendor="Vendor A",
            date="2026-01-05",
            po="12345",
            document_number="A-100",
            document_kind="sales_order",
            item="MAT-1",
            quantity=2,
            unit_cost=400,
            line_amount=800,
            freight=50,
            tax=50,
            document_total=1000,
            priced=True,
        ),
        PurchaseEvidence(
            source="vendor_a_order.pdf",
            vendor="Vendor A",
            date="2026-01-05",
            po="12345",
            document_number="A-100",
            document_kind="sales_order",
            item="MAT-2",
            quantity=1,
            unit_cost=100,
            line_amount=100,
            freight=50,
            tax=50,
            document_total=1000,
            priced=True,
        ),
        PurchaseEvidence(
            source="vendor_b_delivery.pdf",
            vendor="Vendor B",
            date="2026-01-08",
            po="12345",
            document_number="B-200",
            document_kind="delivery_ticket",
            item="SHEET-1",
            quantity=6,
            uom="PC",
            priced=False,
        ),
    )

    summary = summarize_procurement(rows, quote_total=5000)

    assert summary.document_count == 2
    assert summary.priced_document_count == 1
    assert summary.unpriced_document_count == 1
    assert summary.known_purchase_total == 1000
    assert summary.observed_purchase_to_quote_ratio == 0.2
    assert summary.vendor_totals == {"Vendor A": 1000}
    assert summary.documents[0].reconciliation_delta == 0
