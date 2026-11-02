from __future__ import annotations

from auto_bid_builder.opportunities.models import Opportunity
from auto_bid_builder.opportunities.providers import sam
from auto_bid_builder.opportunities import sync as sync_module
from auto_bid_builder.settings import AppSettings, ProviderSettings


def test_sam_pagination_uses_page_index(monkeypatch):
    offsets: list[int] = []

    def fake_search_once(**kwargs):
        offset = int(kwargs["offset"])
        offsets.append(offset)
        if offset == 0:
            rows = [
                {"noticeId": "A", "title": "Millwork A", "naicsCode": "337212"},
                {"noticeId": "B", "title": "Millwork B", "naicsCode": "337212"},
            ]
        elif offset == 1:
            rows = [{"noticeId": "C", "title": "Millwork C", "naicsCode": "337212"}]
        else:
            rows = []
        return {"totalRecords": 3, "opportunitiesData": rows}

    monkeypatch.setattr(sam, "_search_once", fake_search_once)
    rows = sam.search_sam_opportunities(
        api_key="test-key",
        posted_from="09/01/2026",
        posted_to="09/22/2026",
        titles=("millwork",),
        states=("CA",),
        limit_per_query=2,
        max_records_per_query=10,
    )

    assert [row.external_id for row in rows] == ["A", "B", "C"]
    assert offsets == [0, 1]


def test_sam_normalizer_uses_public_ui_link():
    row = sam._normalize(
        {
            "noticeId": "NOTICE-1",
            "title": "Generic Renovation",
            "uiLink": "https://sam.gov/opp/NOTICE-1/view",
            "naicsCode": "337212",
        },
        api_key="test-key",
        hydrate_description=False,
    )
    assert row.url == "https://sam.gov/opp/NOTICE-1/view"
    assert row.naics_code == "337212"


class _FakeSecrets:
    def get(self, provider_id: str, field_name: str):
        if provider_id == "sam" and field_name == "api_key":
            return "saved-key"
        return None


def test_saved_sam_key_is_used_even_if_old_disabled_flag_remains(monkeypatch):
    calls: list[dict] = []

    def fake_search_sam_opportunities(**kwargs):
        calls.append(kwargs)
        return [
            Opportunity(
                source="sam.gov",
                external_id="SAM-1",
                title="Federal interior renovation",
                naics_code="337212",
                state="CA",
                bid_due_date="2026-11-15",
            )
        ]

    monkeypatch.setattr(sync_module, "search_sam_opportunities", fake_search_sam_opportunities)
    settings = AppSettings(
        preferred_states=["CA"],
        lookback_days=30,
        minimum_score=20.0,
        providers=[
            ProviderSettings(
                id="sam",
                label="SAM.gov Contract Opportunities",
                kind="sam",
                enabled=False,
                credential_fields=("api_key",),
            )
        ],
    )

    result = sync_module.sync_opportunities(settings, _FakeSecrets())

    assert len(calls) == 1
    assert calls[0]["api_key"] == "saved-key"
    assert "337212" in calls[0]["naics_codes"]
    assert calls[0]["hydrate_descriptions"] is True
    assert result["total_shown"] == 1
    assert result["opportunities"][0]["opportunity"]["source"] == "sam.gov"
    assert result["source_stats"][0]["auto_enabled_from_saved_key"] is True


def test_sam_normalizer_preserves_nested_job_site_and_poc():
    row = sam._normalize(
        {
            "noticeId": "NOTICE-POC",
            "title": "Federal Casework",
            "data": {
                "placeOfPerformance": {
                    "streetAddress": "500 Federal Plaza",
                    "city": {"name": "Los Angeles"},
                    "state": {"code": "CA"},
                    "zip": "90012",
                },
                "pointOfContact": [
                    {
                        "type": "primary",
                        "title": "Contracting Officer",
                        "fullname": "Taylor Example",
                        "email": "taylor@example.gov",
                        "phone": "555-555-0199",
                    }
                ],
            },
        },
        api_key="test-key",
        hydrate_description=False,
    )
    assert row.street_address == "500 Federal Plaza"
    assert row.city == "Los Angeles"
    assert row.state == "CA"
    assert row.postal_code == "90012"
    assert row.metadata["primary_contact"]["name"] == "Taylor Example"
    assert row.metadata["primary_contact"]["email"] == "taylor@example.gov"


def test_get_sam_opportunity_by_notice_id_uses_notice_and_posted_day(monkeypatch):
    captured: list[str] = []

    def fake_get_json(url: str, **kwargs):
        captured.append(url)
        return {
            "opportunitiesData": [
                {
                    "noticeId": "NOTICE-CSV",
                    "title": "Federal Millwork",
                    "postedDate": "2026-10-31",
                    "responseDeadLine": "2026-11-15T15:00:00-08:00",
                    "resourceLinks": [
                        "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/file-1/download"
                    ],
                    "additionalInfoLink": "https://example.gov/project-documents",
                }
            ]
        }

    monkeypatch.setattr(sam, "_get_json", fake_get_json)
    row = sam.get_sam_opportunity_by_notice_id(
        api_key="saved-key",
        notice_id="NOTICE-CSV",
        posted_date="2026-10-31 12:00:00",
    )

    assert row is not None
    assert row.external_id == "NOTICE-CSV"
    assert row.attachments == (
        "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/file-1/download",
    )
    assert row.url == "https://example.gov/project-documents"
    assert "noticeid=NOTICE-CSV" in captured[0]
    assert "postedFrom=10%2F31%2F2026" in captured[0]
    assert "postedTo=10%2F31%2F2026" in captured[0]


def test_sync_hides_past_due_sam_opportunities(monkeypatch):
    def fake_search_sam_opportunities(**kwargs):
        return [
            Opportunity(
                source="sam.gov",
                external_id="SAM-EXPIRED",
                title="Expired millwork solicitation",
                naics_code="337212",
                state="CA",
                bid_due_date="2026-11-01T12:00:00-08:00",
            ),
            Opportunity(
                source="sam.gov",
                external_id="SAM-FUTURE",
                title="Current millwork solicitation",
                naics_code="337212",
                state="CA",
                bid_due_date="2099-11-15T12:00:00-08:00",
            ),
        ]

    monkeypatch.setattr(sync_module, "search_sam_opportunities", fake_search_sam_opportunities)
    settings = AppSettings(
        preferred_states=["CA"],
        lookback_days=30,
        minimum_score=20.0,
        providers=[
            ProviderSettings(
                id="sam",
                label="SAM.gov Contract Opportunities",
                kind="sam",
                enabled=True,
                credential_fields=("api_key",),
            )
        ],
    )

    result = sync_module.sync_opportunities(settings, _FakeSecrets())

    assert result["expired_filtered"] == 1
    assert result["total_shown"] == 1
    assert result["opportunities"][0]["opportunity"]["external_id"] == "SAM-FUTURE"
