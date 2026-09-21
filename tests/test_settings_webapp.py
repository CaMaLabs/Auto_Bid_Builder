from auto_bid_builder.settings import AppSettings, ProviderSettings
from auto_bid_builder.webapp import render_settings


class FakeSecrets:
    def has(self, provider_id, field_name):
        return provider_id == "sam" and field_name == "api_key"


def test_settings_page_lists_public_and_credentialed_sources():
    settings = AppSettings(providers=[
        ProviderSettings(id="cca_public", label="CCA Public", kind="cca_public", enabled=True),
        ProviderSettings(id="sam", label="SAM.gov", kind="sam", credential_fields=("api_key",)),
    ])
    html = render_settings(settings, FakeSecrets())
    assert "CCA Public" in html
    assert "SAM.gov" in html
    assert "configured" in html
    assert "Preferred states" in html
