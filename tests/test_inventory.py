from pathlib import Path
import zipfile

from auto_bid_builder.ingest.inventory import inventory_path, summarize


def test_zip_inventory_detects_cad_members(tmp_path: Path):
    z = tmp_path / "cad-package.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Index.dwg", b"DWG")
        zf.writestr("General Arrangement.dwg", b"DWG2")
        zf.writestr("notes.txt", b"notes")

    files = inventory_path(z)
    summary = summarize(files)

    assert summary["by_kind"]["archive"] == 1
    assert summary["by_kind"]["cad"] == 2
    assert summary["by_kind"]["other"] == 1
    assert any(f.container == "cad-package.zip" for f in files if f.kind == "cad")
