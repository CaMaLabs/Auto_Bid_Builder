from auto_bid_builder.quote.jti import parse_jti_quote_text


def test_jti_quote_parser_preserves_scope_refs_and_math():
    text = """
QUOTATION
Number Date Description Completion Terms Rep
123456 DEC 22 2025 Sample Project 30/30/30/10 JT
Item Description Qty Each Code Tax Each Amount
1 Cafe: Elevation 8 / A8.00 Library niche cabinet with wood veneer.
Lighting by GCs electrical subcontractor.
1 1000.00 MO 25.00 1025.00
Item Description Qty Each Code Tax Each Amount
2 Conference Support Pantry: Elevations 13/14 A8.01 Bar cabinet.
2 500.00 MO 10.00 1020.00
General Notes Quote Total
Prices are daytime non union installation. Stone by others.
30% Material Deposit due prior to fabrication.
2045.00
Prices are good for a period of Ninety (90) Days from Quotation Date
"""
    quote = parse_jti_quote_text(text)

    assert quote.header.number == "123456"
    assert quote.header.terms == "30/30/30/10"
    assert len(quote.lines) == 2
    assert quote.lines[0].sheet_refs == ("A8.00",)
    assert quote.lines[0].elevation_refs == ("8",)
    assert quote.lines[1].elevation_refs == ("13", "14")
    assert all(line.amount_matches_display for line in quote.lines)
    assert quote.calculated_total == 2045.00
    assert quote.total_matches_display is True
