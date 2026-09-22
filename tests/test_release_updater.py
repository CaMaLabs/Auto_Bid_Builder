from auto_bid_builder.updater import _release_status_from_payload, _version_tuple


def test_version_tuple_parses_tag_versions():
    assert _version_tuple("v0.2.1") > _version_tuple("0.2.0")
    assert _version_tuple("release-1.10.0") > _version_tuple("1.9.9")


def test_release_payload_selects_portable_asset():
    payload = {
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/CaMaLabs/Auto_Bid_Builder/releases/tag/v0.3.0",
        "assets": [
            {
                "name": "AutoBidBuilder-portable.zip",
                "browser_download_url": "https://example.invalid/AutoBidBuilder-portable.zip",
            }
        ],
    }
    status = _release_status_from_payload(payload, current_version="0.2.0")
    assert status.update_available is True
    assert status.mode == "release"
    assert status.remote_version == "0.3.0"
    assert status.download_url.endswith("AutoBidBuilder-portable.zip")
