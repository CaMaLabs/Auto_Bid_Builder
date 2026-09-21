from pathlib import Path

from auto_bid_builder.settings import load_settings, save_settings


def test_update_settings_round_trip(tmp_path: Path):
    settings = load_settings(tmp_path)
    settings.check_updates_on_startup = False
    settings.auto_update = True
    settings.update_branch = "stable"
    save_settings(settings, tmp_path)

    loaded = load_settings(tmp_path)
    assert loaded.check_updates_on_startup is False
    assert loaded.auto_update is True
    assert loaded.update_branch == "stable"
    assert loaded.providers
