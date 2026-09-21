from auto_bid_builder.revisions.impact import diff_revision_signals


def test_revision_diff_finds_estimator_relevant_changes_without_full_line_diff():
    old = """
WD2 floating wood shelves 1'-7".
Decorative wood beam. Detail 4/A11.41.
"""
    new = """
WD2 floating wood shelves 1'-3". V.I.F. COORD. W/ EQUIP.
FILLER PANEL BETWEEN EQUIPMENT.
NOTCH BASE CABINET BOX TO RECEIVE CONTINUOUS HORIZONTAL MILLWORK PANEL.
RFI #58
Decorative wood beam. Detail 2/A11.41.
"""
    impact = diff_revision_signals(old, new)

    assert impact.has_scope_relevant_change
    assert "58" in impact.added_rfi_refs
    assert "vif" in impact.added_phrases
    assert "coordinate_with_equipment" in impact.added_phrases
    assert "filler_panel" in impact.added_phrases
    assert "notch_cabinet" in impact.added_phrases
    assert "1'-3\"" in impact.added_dimensions
    assert "1'-7\"" in impact.removed_dimensions
