from pathlib import Path

from auto_bid_builder.updater import _build_update_script, _release_status_from_payload, _version_tuple


def test_version_tuple_parses_tag_versions():
    assert _version_tuple("v0.2.1") > _version_tuple("0.2.0")
    assert _version_tuple("release-1.10.0") > _version_tuple("1.9.9")


def test_release_payload_prefers_guided_installer():
    payload = {
        "tag_name": "v0.4.2",
        "html_url": "https://github.com/CaMaLabs/Auto_Bid_Builder/releases/tag/v0.4.2",
        "assets": [
            {
                "name": "AutoBidBuilder-portable.zip",
                "browser_download_url": "https://example.invalid/AutoBidBuilder-portable.zip",
            },
            {
                "name": "JTI_Auto_Bid_Builder_Setup.exe",
                "browser_download_url": "https://example.invalid/JTI_Auto_Bid_Builder_Setup.exe",
            },
        ],
    }
    status = _release_status_from_payload(payload, current_version="0.4.1")
    assert status.update_available is True
    assert status.mode == "release"
    assert status.remote_version == "0.4.2"
    assert status.package_kind == "installer"
    assert status.download_url.endswith("JTI_Auto_Bid_Builder_Setup.exe")


def test_release_payload_falls_back_to_portable_package():
    payload = {
        "tag_name": "v0.4.2",
        "assets": [
            {
                "name": "AutoBidBuilder-portable.zip",
                "browser_download_url": "https://example.invalid/AutoBidBuilder-portable.zip",
            }
        ],
    }
    status = _release_status_from_payload(payload, current_version="0.4.1")
    assert status.package_kind == "portable"
    assert status.download_url.endswith("AutoBidBuilder-portable.zip")


def test_update_script_waits_runs_installer_logs_and_relaunches():
    script = _build_update_script(
        package=Path(r"C:\Temp\JTI_Auto_Bid_Builder_Setup.exe"),
        package_kind="installer",
        exe_path=Path(r"C:\Users\Example\AppData\Local\JTI\AutoBidBuilder\AutoBidBuilder.exe"),
        install_dir=Path(r"C:\Users\Example\AppData\Local\JTI\AutoBidBuilder"),
        pid=1234,
        log_path=Path(r"C:\Users\Example\AppData\Local\JTI\AutoBidBuilder\update.log"),
    )
    assert "while (Get-Process -Id $PidToWait" in script
    assert "'/VERYSILENT'" in script
    assert "Start-Process -FilePath $Exe" in script
    assert "UPDATE FAILED" in script
