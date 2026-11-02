from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .deadlines import is_past_due
from .models import Opportunity
from .score import OpportunityScore, score_opportunity


_SAM_REQUIRED_COLUMNS = {"NoticeId", "Title", "PostedDate", "NaicsCode", "Link", "Description"}


def _text(row: dict[str, str], key: str) -> str:
    return str(row.get(key) or "").strip()


def looks_like_sam_full_csv(fieldnames: list[str] | tuple[str, ...] | None) -> bool:
    return bool(fieldnames) and _SAM_REQUIRED_COLUMNS.issubset(set(fieldnames or ()))


def _normalize_sam_csv_row(row: dict[str, str], *, source_file: str) -> Opportunity | None:
    notice_id = _text(row, "NoticeId")
    title = _text(row, "Title")
    if not notice_id and not title:
        return None

    organization = _text(row, "Department/Ind.Agency") or _text(row, "Sub-Tier") or None
    url = _text(row, "Link") or _text(row, "AdditionalInfoLink") or None
    if url and not url.lower().startswith(("http://", "https://")):
        url = None

    return Opportunity(
        source="sam.gov CSV",
        external_id=notice_id or _text(row, "Sol#") or title,
        title=title or "(untitled SAM opportunity)",
        description=_text(row, "Description"),
        organization=organization,
        posted_date=_text(row, "PostedDate") or None,
        bid_due_date=_text(row, "ResponseDeadLine") or None,
        street_address=_text(row, "PopStreetAddress") or None,
        city=_text(row, "PopCity") or _text(row, "City") or None,
        state=_text(row, "PopState") or _text(row, "State") or None,
        postal_code=_text(row, "PopZip") or _text(row, "ZipCode") or None,
        naics_code=_text(row, "NaicsCode") or None,
        classification_code=_text(row, "ClassificationCode") or None,
        url=url,
        attachments=(),
        metadata={
            "solicitation_number": _text(row, "Sol#") or None,
            "notice_type": _text(row, "Type") or None,
            "base_type": _text(row, "BaseType") or None,
            "set_aside": _text(row, "SetASide") or None,
            "set_aside_code": _text(row, "SetASideCode") or None,
            "active": _text(row, "Active") or None,
            "office": _text(row, "Office") or None,
            "award_number": _text(row, "AwardNumber") or None,
            "award_date": _text(row, "AwardDate") or None,
            "award_value": _text(row, "Award$") or None,
            "additional_info_link": _text(row, "AdditionalInfoLink") or None,
            "primary_contact": {
                "title": _text(row, "PrimaryContactTitle") or None,
                "name": _text(row, "PrimaryContactFullname") or None,
                "email": _text(row, "PrimaryContactEmail") or None,
                "phone": _text(row, "PrimaryContactPhone") or None,
                "fax": _text(row, "PrimaryContactFax") or None,
            },
            "secondary_contact": {
                "title": _text(row, "SecondaryContactTitle") or None,
                "name": _text(row, "SecondaryContactFullname") or None,
                "email": _text(row, "SecondaryContactEmail") or None,
                "phone": _text(row, "SecondaryContactPhone") or None,
                "fax": _text(row, "SecondaryContactFax") or None,
            },
            "imported_from_csv": source_file,
        },
    )


def import_sam_opportunity_csv(
    path: str | Path,
    *,
    preferred_states: set[str] | None = None,
    minimum_score: float = 0.0,
    now: datetime | None = None,
) -> dict:
    """Stream a SAM.gov full contract-opportunity CSV into the normal review queue.

    Large exports are processed row-by-row so a 200+ MB file does not need to be
    loaded into memory. Only rows meeting the current review threshold are retained.
    """
    source = Path(path)
    preferred = {str(x).upper() for x in (preferred_states or set())}
    scanned = 0
    normalized = 0
    expired_filtered = 0
    deduped: dict[str, OpportunityScore] = {}

    with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        if not looks_like_sam_full_csv(reader.fieldnames):
            missing = sorted(_SAM_REQUIRED_COLUMNS - set(reader.fieldnames or ()))
            raise ValueError(
                "This CSV does not look like a SAM.gov Contract Opportunities full export. "
                + ("Missing: " + ", ".join(missing) if missing else "")
            )

        for raw in reader:
            scanned += 1
            opportunity = _normalize_sam_csv_row(raw, source_file=source.name)
            if opportunity is None:
                continue
            normalized += 1
            if is_past_due(opportunity.bid_due_date, now=now):
                expired_filtered += 1
                continue
            scored = score_opportunity(opportunity, preferred_states=preferred)
            if scored.score < float(minimum_score):
                continue
            key = (opportunity.external_id or opportunity.title).lower()
            previous = deduped.get(key)
            if previous is None or scored.score > previous.score:
                deduped[key] = scored

    shown = sorted(
        deduped.values(),
        key=lambda row: (
            -row.score,
            row.opportunity.bid_due_date or "9999",
            row.opportunity.title.lower(),
        ),
    )
    return {
        "sources": ["SAM.gov CSV import"],
        "source_stats": [
            {
                "source": "SAM.gov CSV import",
                "file": source.name,
                "scanned": scanned,
                "normalized": normalized,
                "expired_filtered": expired_filtered,
                "shown": len(shown),
            }
        ],
        "errors": [],
        "total_normalized": normalized,
        "minimum_score": float(minimum_score),
        "total_shown": len(shown),
        "opportunities": [row.to_dict() for row in shown],
        "imported_file": str(source),
        "rows_scanned": scanned,
        "expired_filtered": expired_filtered,
    }
