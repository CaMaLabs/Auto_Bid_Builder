from auto_bid_builder.extract.signals import extract_signals, has_scope_trigger


def test_millworker_sheet_becomes_scope_trigger():
    text = """
    Provided by Millworker
    FREESTANDING HANGING BAR
    MATERIALS: black metal powder coated.
    Rod length to be determined by Millworker in order to avoid wobbling.
    Metal platform 5 mm.
    This drawing shows an architectural concept and shall not be used for construction.
    Dimensions must be verified and approved by registered engineers.
    """
    signals = extract_signals(text)

    assert has_scope_trigger(signals)
    assert any(s.value == "powder-coated metal" for s in signals)
    assert any(s.value == "concept_not_for_construction" for s in signals)
    assert any(s.value == "dimension_verification_required" for s in signals)
    assert any(s.kind == "dimension_mm" and s.value == "5" for s in signals) is False
    # Intentionally ignore one-digit mm values because isolated detail numbers are a
    # common false positive. Small dimensions need drawing-aware extraction.


def test_material_sample_language_is_detected():
    text = "RIBBED MDF (yellow)\nPOWDER COATED METAL (black)\nTUFTED WOOL CARPET (off white)"
    values = {s.value for s in extract_signals(text) if s.kind == "material"}
    assert {"ribbed MDF", "powder-coated metal", "wool carpet"} <= values
