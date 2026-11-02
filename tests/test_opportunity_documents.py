from pathlib import Path

from auto_bid_builder.bid_workspace import create_workspace, load_manifest
from auto_bid_builder.opportunities import documents
from auto_bid_builder.opportunities.models import Opportunity


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


def test_listing_discovery_follows_one_nested_document_page(monkeypatch):
    pages = {
        "https://example.com/project/1": (
            "https://example.com/project/1",
            '<html><body>'
            '<a href="/about">About</a>'
            '<a href="/bid-documents">Bid Documents</a>'
            '</body></html>',
        ),
        "https://example.com/bid-documents": (
            "https://example.com/bid-documents",
            '<html><body>'
            '<a href="/files/plans.pdf">Plans</a>'
            '<a href="/download?id=42">Download Specifications</a>'
            '</body></html>',
        ),
    }

    monkeypatch.setattr(documents, "_is_public_http_url", lambda _url: True)
    monkeypatch.setattr(
        documents,
        "_read_html",
        lambda url, **kwargs: pages[url],
    )

    found = documents.discover_listing_files("https://example.com/project/1")

    assert "https://example.com/files/plans.pdf" in found
    assert "https://example.com/download?id=42" in found
    assert "https://example.com/about" not in found


def test_listing_discovery_does_not_recurse_beyond_nested_document_page(monkeypatch):
    pages = {
        "https://example.com/project/1": (
            "https://example.com/project/1",
            '<a href="/bid-documents">Bid Documents</a>',
        ),
        "https://example.com/bid-documents": (
            "https://example.com/bid-documents",
            '<a href="/more-documents">More Documents</a>',
        ),
    }

    monkeypatch.setattr(documents, "_is_public_http_url", lambda _url: True)
    monkeypatch.setattr(documents, "_read_html", lambda url, **kwargs: pages[url])

    found = documents.discover_listing_files("https://example.com/project/1")

    assert found == []


def test_intermediate_page_detection_requires_same_host_and_document_hint():
    assert documents._looks_like_document_page(
        "https://example.com/project/123/documents",
        "Project Documents",
        parent_url="https://example.com/project/123",
    )
    assert not documents._looks_like_document_page(
        "https://example.com/about",
        "About",
        parent_url="https://example.com/project/123",
    )
    assert not documents._looks_like_document_page(
        "https://other.example.net/documents",
        "Bid Documents",
        parent_url="https://example.com/project/123",
    )


def test_download_action_detection_accepts_extensionless_attachment_links():
    assert documents._looks_like_download_action(
        "https://example.com/file/download?id=123",
        "Download Plans",
    )
    assert documents._looks_like_download_action(
        "https://example.com/attachment?id=456",
        "Attachment",
    )
    assert not documents._looks_like_download_action(
        "https://example.com/register",
        "Register",
    )


def test_caleprocure_view_event_package_button_target_is_detected():
    html = (
        '<html><body>'
        '<button onclick="window.location.href=\'/PSRelay/event-package?AUC_ID=123\'">'
        'View Event Package'
        '</button>'
        '</body></html>'
    )
    target = documents._find_caleprocure_event_package_target(
        "https://caleprocure.ca.gov/event/7760/123",
        html,
    )
    assert target == "https://caleprocure.ca.gov/PSRelay/event-package?AUC_ID=123"


def test_caleprocure_view_event_package_formaction_is_detected():
    html = (
        '<html><body>'
        '<button formaction="/PSRelay/package?AUC_ID=456" aria-label="View Event Package">'
        'View Event Package'
        '</button>'
        '</body></html>'
    )
    target = documents._find_caleprocure_event_package_target(
        "https://caleprocure.ca.gov/event/7760/456",
        html,
    )
    assert target == "https://caleprocure.ca.gov/PSRelay/package?AUC_ID=456"


def test_caleprocure_view_event_package_without_target_falls_back():
    html = '<button type="button">View Event Package</button>'
    target = documents._find_caleprocure_event_package_target(
        "https://caleprocure.ca.gov/event/7760/789",
        html,
    )
    assert target is None
    fallback = documents._caleprocure_package_url(
        "https://caleprocure.ca.gov/event/7760/789"
    )
    assert fallback is not None
    assert "AUC_ID=789" in fallback


def test_sam_csv_pull_hydrates_notice_and_downloads_resource_links(tmp_path: Path, monkeypatch):
    row = {
        "opportunity": {
            "source": "sam.gov CSV",
            "external_id": "NOTICE-CSV",
            "title": "Federal Millwork",
            "posted_date": "2026-10-31 12:00:00",
            "bid_due_date": "2026-11-20T12:00:00-08:00",
            "url": "https://sam.gov/workspace/contract/opp/NOTICE-CSV/view",
            "attachments": [],
            "metadata": {"solicitation_number": "SOL-CSV"},
        }
    }
    root = create_workspace(tmp_path, row)
    calls: list[dict] = []

    def fake_hydrate(**kwargs):
        calls.append(kwargs)
        return Opportunity(
            source="sam.gov",
            external_id="NOTICE-CSV",
            title="Federal Millwork",
            posted_date="2026-10-31",
            bid_due_date="2026-11-20T12:00:00-08:00",
            url="https://example.gov/bid-documents",
            attachments=(
                "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/file-1/download",
            ),
            metadata={
                "solicitation_number": "SOL-CSV",
                "additional_info_link": "https://example.gov/bid-documents",
            },
        )

    monkeypatch.setattr(documents, "get_sam_opportunity_by_notice_id", fake_hydrate)
    monkeypatch.setattr(documents, "_is_public_http_url", lambda _url: True)
    monkeypatch.setattr(documents, "discover_listing_files", lambda url, **kwargs: [])

    def fake_download(url, destination, **kwargs):
        if "file-1" not in url:
            return None
        target = destination / "plans.pdf"
        target.write_bytes(b"%PDF-1.4\nsynthetic plans\n%%EOF")
        return target

    monkeypatch.setattr(documents, "_download", fake_download)

    result = documents.pull_opportunity_documents(
        root,
        row,
        sam_api_key="saved-key",
    )

    assert calls == [
        {
            "api_key": "saved-key",
            "notice_id": "NOTICE-CSV",
            "posted_date": "2026-10-31 12:00:00",
            "hydrate_description": False,
        }
    ]
    assert result.downloaded_count == 1
    assert (root / "bid_docs" / "plans.pdf").exists()

    manifest = load_manifest(root)
    stored = manifest["opportunity"]["opportunity"]
    assert stored["attachments"] == [
        "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/file-1/download"
    ]
    assert stored["metadata"]["additional_info_link"] == "https://example.gov/bid-documents"


def test_sam_csv_pull_explains_missing_api_key(tmp_path: Path):
    row = {
        "opportunity": {
            "source": "sam.gov CSV",
            "external_id": "NOTICE-NOKEY",
            "title": "Federal Millwork",
            "url": "",
            "attachments": [],
        }
    }
    root = create_workspace(tmp_path, row)

    result = documents.pull_opportunity_documents(root, row)

    assert result.downloaded_count == 0
    assert any("SAM.gov API key" in error for error in result.errors)
