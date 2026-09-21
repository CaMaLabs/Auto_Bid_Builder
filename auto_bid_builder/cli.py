from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from auto_bid_builder.analysis.scope import scan_pdf
from auto_bid_builder.ingest.pdf import extract_pdf_pages, index_pages_by_sheet
from auto_bid_builder.project_docs import audit_project_folder, project_audit_markdown
from auto_bid_builder.quote.jti import parse_jti_quote_pdf
from auto_bid_builder.report import revision_report_markdown
from auto_bid_builder.revisions.map_quote import build_sheet_impacts, map_impacts_to_quote, sheet_impacts_to_dict


def _json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def cmd_parse_quote(args: argparse.Namespace) -> int:
    quote = parse_jti_quote_pdf(args.quote)
    data = quote.to_dict()
    if args.output:
        _json(Path(args.output), data)
    else:
        print(json.dumps(data, indent=2))
    if not quote.lines or quote.total_matches_display is False or not all(x.amount_matches_display for x in quote.lines):
        return 2
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.input)
    files = [root] if root.is_file() else sorted(root.glob("*.pdf"))
    rows = []
    for path in files:
        rows.extend(asdict(r) for r in scan_pdf(path))
    rows.sort(key=lambda x: (-x["relevance_score"], x["source"], x["page"]))
    _json(Path(args.output), {"pages": rows})
    return 0


def cmd_project_audit(args: argparse.Namespace) -> int:
    docs = audit_project_folder(args.input)
    payload = {"documents": [doc.to_dict() for doc in docs]}
    output = Path(args.output)
    _json(output, payload)
    markdown = Path(args.markdown) if args.markdown else output.with_suffix(".md")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(project_audit_markdown(docs), encoding="utf-8")
    print(markdown)
    return 0 if docs else 2


def _baseline_index(folder: Path, sheets: set[str]):
    out = {}
    for pdf in sorted(folder.glob("*.pdf")):
        pages = extract_pdf_pages(pdf)
        for page in pages:
            if page.sheet in sheets and page.sheet not in out:
                out[page.sheet] = page
    return out


def cmd_revision_audit(args: argparse.Namespace) -> int:
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    quote = parse_jti_quote_pdf(args.quote)
    needed = {s for line in quote.lines for s in line.sheet_refs}
    baseline = _baseline_index(Path(args.baseline_dir), needed)
    revision = index_pages_by_sheet(extract_pdf_pages(args.revision))
    sheet_impacts = build_sheet_impacts(baseline, revision)
    line_impacts = map_impacts_to_quote(quote, sheet_impacts)
    _json(outdir / "quote.json", quote.to_dict())
    _json(
        outdir / "revision_audit.json",
        {
            "baseline_sheets_found": sorted(baseline),
            "revision_sheets_found": sorted(revision),
            "sheet_impacts": sheet_impacts_to_dict(sheet_impacts),
            "quote_line_impacts": [asdict(x) for x in line_impacts],
        },
    )
    (outdir / "revision_audit.md").write_text(
        revision_report_markdown(quote, sheet_impacts, line_impacts), encoding="utf-8"
    )
    print(outdir / "revision_audit.md")
    return 0 if quote.lines else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="auto-bid-builder", description="Evidence-backed JTI millwork bid assistant")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("parse-quote", help="Parse a JTI quotation PDF into auditable JSON")
    q.add_argument("quote")
    q.add_argument("-o", "--output")
    q.set_defaults(func=cmd_parse_quote)

    s = sub.add_parser("scan", help="Rank millwork-relevant pages in a bid package")
    s.add_argument("input")
    s.add_argument("-o", "--output", default="bid_scan.json")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("project-audit", help="Classify project lifecycle PDFs and surface field-measure/submittal/RFI review states")
    a.add_argument("input", help="PDF file or folder of project PDFs")
    a.add_argument("-o", "--output", default="project_audit.json")
    a.add_argument("--markdown")
    a.set_defaults(func=cmd_project_audit)

    r = sub.add_parser("revision-audit", help="Map revised drawing signals back to quoted JTI line items")
    r.add_argument("--quote", required=True)
    r.add_argument("--baseline-dir", required=True)
    r.add_argument("--revision", required=True)
    r.add_argument("--output-dir", default="auto_bid_output")
    r.set_defaults(func=cmd_revision_audit)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
