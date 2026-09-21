from auto_bid_builder.ingest.pdf import detect_sheet_id
from auto_bid_builder.quote.jti import parse_jti_quote_text
from auto_bid_builder.revisions.impact import diff_revision_signals


def test_quote_parser_layout_text():
    text = '''QUOTATION
Number Date Description Completion Terms Rep
123456 DEC 22 2025 Sample Project 30/30/30/10 JT
Item Description Qty Each Code Tax Each Amount
1 Cafe: Elevation 8 / A8.00 Library niche cabinet 1 1000.00 MO 25.00 1025.00
with WD2 exterior.
General Notes Quote Total
Daytime install 1025.00
Prices are good for a period of Ninety (90) Days from Quotation Date'''
    quote = parse_jti_quote_text(text)
    assert len(quote.lines) == 1
    assert quote.lines[0].sheet_refs == ("A8.00",)
    assert quote.total_matches_display is True


def test_compiled_sheet_detection_prefers_tail_titleblock():
    text = 'A8.01 callout\nA11.64 detail\nproject text\nA8.00\nENLARGED PLANS & ELEVATIONS'
    assert detect_sheet_id(text) == 'A8.00'


def test_revision_catches_rfi_and_notch():
    old = 'WD2 V.I.F. filler panel 1 1/2"'
    new = 'WD2 V.I.F. filler panel RFI #58 NOTCH BASE CABINET BOX 2"'
    diff = diff_revision_signals(old, new)
    assert diff.added_rfi_refs == ("58",)
    assert "notch_cabinet" in diff.added_phrases
