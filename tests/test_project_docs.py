from auto_bid_builder.project_docs import classify_document, project_audit_markdown


def test_classifies_project_lifecycle_documents():
    assert classify_document("Orrick - Field Measure.pdf", "FIELD MEASURE 03.06.26") == "field_measure"
    assert classify_document("ASK-001.pdf", "ASK-001 RCP Ceiling Height Update 2/19/2026") == "ask"
    assert classify_document("JTI Shop Drawings Revised.pdf", "SHOP DRAWINGS REVISED") == "shop_drawing_revision"
    assert classify_document("Orrick RFI.pdf", "") == "rfi"
    assert classify_document("millwork submittal.pdf", "SUBMITTAL #06 40 00-2.0") == "submittal"


def test_audit_report_keeps_human_review_boundary():
    from auto_bid_builder.project_docs import ProjectDocument

    docs = (
        ProjectDocument(
            source="millwork_samples.pdf",
            kind="submittal",
            page_count=2,
            project="25-G018 - Orrick - Santa Monica",
            issue_date="02/19/2026",
            status="Revise and Resubmit",
            spec_section="06 40 00 - Millwork",
            responsible_contractor="Jeffrey Trott Industries, Inc.",
            finish_codes=("PL1", "PL2", "PL3", "MTL1", "MEL1"),
            review_actions=("revise_and_resubmit", "partial_finish_approval"),
            flags=("unresolved_submittal_review", "finish_match_requirement"),
        ),
    )
    report = project_audit_markdown(docs)
    assert "Review queue" in report
    assert "millwork_samples.pdf" in report
    assert "contractual conclusions" in report
