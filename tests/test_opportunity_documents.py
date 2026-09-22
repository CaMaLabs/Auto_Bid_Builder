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
