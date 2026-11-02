from auto_bid_builder.ingest.pdf import detect_sheet_id


def test_detect_sheet_id_prefers_actual_title_block_sheet_over_legend_example():
    text = """
SYMBOL LEGEND
DETAIL REFERENCE
1
A3.01
SHEET NUMBER
GENERAL NOTES
PROJECT DATA AND CODE ANALYSIS
T0.4
ISSUE DATE: APRIL 15, 2026
"""
    assert detect_sheet_id(text) == "T0.4"


def test_detect_sheet_id_supports_letter_suffix():
    text = """
SINGLE LINE DIAGRAM
E0.3A
ISSUE DATE
"""
    assert detect_sheet_id(text) == "E0.3A"
