from auto_bid_builder.opportunities.models import Opportunity
from auto_bid_builder.opportunities.providers import sam
from auto_bid_builder.opportunities.score import score_opportunity


def test_jti_fit_scoring_rewards_millwork_evidence_and_documents():
    opp = Opportunity(
        source="synthetic",
        external_id="1",
        title="Architectural Millwork and Casework Renovation",
        description="Provide wood veneer wall panels and custom cabinetry.",
        state="CA",
        bid_due_date="2026-10-01",
        attachments=("https://example.invalid/plans.pdf",),
    )
    row = score_opportunity(opp, preferred_states={"CA"})
    assert row.score >= 45
    assert row.tier == "strong_review"
    assert any("architectural millwork" in reason for reason in row.reasons)


def test_sam_provider_normalizes_and_deduplicates(monkeypatch):
    payload = {
        "opportunitiesData": [
            {
                "noticeId": "abc123",
                "title": "Custom Casework",
                "solicitationNumber": "SOL-1",
                "fullParentPathName": "TEST AGENCY.TEST OFFICE",
                "postedDate": "2026-09-20",
                "responseDeadLine": "2026-10-01T17:00:00-07:00",
                "naicsCode": "337212",
                "classificationCode": "Z2AA",
                "active": "Yes",
                "placeOfPerformance": {
                    "city": {"name": "Los Angeles"},
                    "state": {"code": "CA"},
                    "zip": "90012",
                },
                "resourceLinks": ["https://example.invalid/spec.pdf"],
                "description": "https://example.invalid/description",
            }
        ]
    }

    monkeypatch.setattr(sam, "_search_once", lambda **kwargs: payload)
    rows = sam.search_sam_opportunities(
        api_key="test-key",
        posted_from="09/01/2026",
        posted_to="09/21/2026",
        titles=("millwork", "casework"),
        states=("CA",),
    )
    assert len(rows) == 1
    opp = rows[0]
    assert opp.external_id == "abc123"
    assert opp.title == "Custom Casework"
    assert opp.state == "CA"
    assert opp.naics_code == "337212"
    assert len(opp.attachments) == 1
