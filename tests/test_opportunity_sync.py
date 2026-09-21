from auto_bid_builder.opportunities.models import Opportunity
from auto_bid_builder.opportunities.sync import sync_opportunities
from auto_bid_builder.settings import AppSettings, ProviderSettings


def test_sync_public_sources_and_score(monkeypatch):
    opportunity = Opportunity(
        source="test",
        external_id="1",
        title="Architectural millwork and casework package",
        description="Custom cabinetry Division 06 40 00",
        state="CA",
    )
    monkeypatch.setattr("auto_bid_builder.opportunities.sync.fetch_cca_opportunities", lambda *args: [opportunity])
    settings = AppSettings(
        preferred_states=["CA"],
        minimum_score=20,
        providers=[ProviderSettings(id="cca_public", label="CCA", kind="cca_public", enabled=True)],
    )
    result = sync_opportunities(settings)
    assert result["errors"] == []
    assert result["total_normalized"] == 1
    assert result["total_shown"] == 1
    assert result["opportunities"][0]["opportunity"]["title"].startswith("Architectural millwork")


def test_unimplemented_enabled_provider_is_reported_without_crash():
    settings = AppSettings(
        providers=[ProviderSettings(id="dodge", label="Dodge", kind="dodge", enabled=True)],
        minimum_score=0,
    )
    result = sync_opportunities(settings)
    assert result["total_normalized"] == 0
    assert "adapter not implemented" in result["errors"][0]["error"]
