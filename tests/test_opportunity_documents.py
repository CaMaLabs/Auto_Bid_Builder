from pathlib import Path

from auto_bid_builder.bid_workspace import create_workspace, load_manifest
from auto_bid_builder.opportunities import documents


def test_pull_opportunity_documents_downloads_and_registers_files(tmp_path: Path, monkeypatch):
    row = {
        "opportunity": {
            "source": "Synthetic bid board",
            "external_id": "SYN-1",
            "title": "Synthetic Retail TI",
            "url": "https://example.com/project/1",
            "attachments": [],
        }
    }
    root = create_workspace(tmp_path, row)

    monkeypatch.setattr(
        documents,
        "discover_listing_files",
        lambda url, **kwargs: ["https://example.com/files/plans.pdf", "https://example.com/files/specs.zip"],
    )

    def fake_download(url, destination, **kwargs):
        name = Path(url).name
        target = destination / name
        if name.endswith(".pdf"):
            target.write_bytes(b"%PDF-1.4\nsynthetic\n%%EOF")
        else:
            import zipfile
            with zipfile.ZipFile(target, "w") as zf:
                zf.writestr("addendum.txt", "synthetic")
        return target

    monkeypatch.setattr(documents, "_download", fake_download)
    result = documents.pull_opportunity_documents(root, row)

    assert result.downloaded_count >= 2
    assert (root / "bid_docs" / "plans.pdf").exists()
    assert (root / "bid_docs" / "specs.zip").exists()
    assert (root / "bid_docs" / "specs_extracted" / "addendum.txt").exists()
    manifest = load_manifest(root)
    assert manifest["workflow"]["documents_added"] is True
    stored = {item["stored_name"] for item in manifest["documents"]}
    assert "plans.pdf" in stored
    assert "specs.zip" in stored


def test_pull_respects_login_boundary_when_no_public_files(tmp_path: Path, monkeypatch):
    row = {"opportunity": {"title": "Login-only job", "url": "https://example.com/login"}}
    root = create_workspace(tmp_path, row)
    monkeypatch.setattr(documents, "discover_listing_files", lambda url, **kwargs: [])
    result = documents.pull_opportunity_documents(root, row)
    assert result.downloaded_count == 0
    assert result.errors == []


def test_caleprocure_event_url_builds_public_event_package_route():
    url = "https://caleprocure.ca.gov/event/7760/0000034413"
    assert documents._caleprocure_event_parts(url) == ("7760", "0000034413")
    package = documents._caleprocure_package_url(url)
    assert package is not None
    assert "BUSINESS_UNIT=7760" in package
    assert "AUC_ID=0000034413" in package
    assert "AUC_RESP_INQ_AUC" in package


def test_caleprocure_download_link_detection_accepts_attachment_actions():
    assert documents._looks_like_caleprocure_download(
        "https://caleprocure.ca.gov/psc/attachment-handler?x=1",
        "Download Attachment",
    )
    assert documents._looks_like_caleprocure_download(
        "https://caleprocure.ca.gov/files/project-manual.pdf",
        "Project Manual",
    )
    assert not documents._looks_like_caleprocure_download(
        "https://caleprocure.ca.gov/pages/bidder-vendor.aspx",
        "Register as bidder",
    )


def test_pull_uses_caleprocure_event_package_discovery(tmp_path: Path, monkeypatch):
    row = {
        "opportunity": {
            "source": "California DGS",
            "external_id": "0000034413",
            "title": "Synthetic Cal eProcure project",
            "url": "https://caleprocure.ca.gov/event/7760/0000034413",
            "attachments": [],
        }
    }
    root = create_workspace(tmp_path, row)
    monkeypatch.setattr(documents, "_cookie_opener", lambda: object())
    monkeypatch.setattr(documents, "discover_listing_files", lambda url, **kwargs: [])
    monkeypatch.setattr(
        documents,
        "discover_caleprocure_event_files",
        lambda url, **kwargs: ["https://caleprocure.ca.gov/public/plans.pdf"],
    )

    def fake_download(url, destination, **kwargs):
        target = destination / "plans.pdf"
        target.write_bytes(b"%PDF-1.4\nsynthetic\n%%EOF")
        return target

    monkeypatch.setattr(documents, "_download", fake_download)
    result = documents.pull_opportunity_documents(root, row)
    assert result.downloaded_count == 1
    assert (root / "bid_docs" / "plans.pdf").exists()
