from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import json
import zipfile


_KIND_BY_SUFFIX = {
    ".pdf": "pdf",
    ".dwg": "cad",
    ".dxf": "cad",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".csv": "spreadsheet",
    ".docx": "document",
    ".doc": "document",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".zip": "archive",
}


@dataclass(frozen=True)
class PackageFile:
    path: str
    kind: str
    suffix: str
    size_bytes: int | None
    container: str | None = None


def classify_path(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return _KIND_BY_SUFFIX.get(suffix, "other")


def _record(path: Path, *, container: str | None = None, size_bytes: int | None = None) -> PackageFile:
    return PackageFile(
        path=path.as_posix(),
        kind=classify_path(path),
        suffix=path.suffix.lower(),
        size_bytes=size_bytes,
        container=container,
    )


def inventory_path(path: str | Path, *, expand_zip: bool = True) -> list[PackageFile]:
    """Inventory a file, directory, or ZIP without extracting proprietary inputs."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    if p.is_dir():
        out: list[PackageFile] = []
        for child in sorted(x for x in p.rglob("*") if x.is_file()):
            if expand_zip and child.suffix.lower() == ".zip":
                out.extend(inventory_path(child, expand_zip=True))
            else:
                out.append(_record(child, size_bytes=child.stat().st_size))
        return out

    if expand_zip and p.suffix.lower() == ".zip":
        out = [_record(p, size_bytes=p.stat().st_size)]
        with zipfile.ZipFile(p) as zf:
            for info in sorted((i for i in zf.infolist() if not i.is_dir()), key=lambda i: i.filename.lower()):
                member = Path(info.filename)
                out.append(_record(member, container=p.name, size_bytes=info.file_size))
        return out

    return [_record(p, size_bytes=p.stat().st_size)]


def summarize(files: Iterable[PackageFile]) -> dict[str, object]:
    rows = list(files)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.kind] = counts.get(row.kind, 0) + 1
    return {
        "file_count": len(rows),
        "by_kind": dict(sorted(counts.items())),
        "files": [asdict(r) for r in rows],
    }


def write_manifest(files: Iterable[PackageFile], destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summarize(files), indent=2), encoding="utf-8")
    return destination
