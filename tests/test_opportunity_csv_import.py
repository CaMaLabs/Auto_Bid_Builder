import csv
from pathlib import Path

from auto_bid_builder.opportunities.import_csv import import_sam_opportunity_csv


FIELDS = [
    "NoticeId", "Title", "Sol#", "Department/Ind.Agency", "Sub-Tier",
    "PostedDate", "Type", "BaseType", "SetASideCode", "SetASide",
    "ResponseDeadLine", "NaicsCode", "ClassificationCode", "PopCity",
    "PopState", "PopZip", "Active", "Office", "AwardNumber", "AwardDate",
    "Award$", "AdditionalInfoLink", "Link", "Description",
]


def _write_csv(path: Path) -> None:
    rows = [
        {
            "NoticeId": "relevant-1",
            "Title": "Federal architectural millwork package",
            "Sol#": "SOL-1",
            "Department/Ind.Agency": "TEST AGENCY",
            "Sub-Tier": "TEST SUBTIER",
            "PostedDate": "2026-11-01 12:00:00",
            "Type": "Solicitation",
            "BaseType": "Solicitation",
            "SetASideCode": "",
            "SetASide": "",
            "ResponseDeadLine": "2026-11-20T12:00:00-08:00",
            "NaicsCode": "337212",
            "ClassificationCode": "Y1AA",
            "PopCity": "Los Angeles",
            "PopState": "CA",
            "PopZip": "90012",
            "Active": "Yes",
            "Office": "TEST OFFICE",
            "AwardNumber": "",
            "AwardDate": "",
            "Award$": "",
            "AdditionalInfoLink": "",
            "Link": "https://sam.gov/workspace/contract/opp/relevant-1/view",
            "Description": "Provide architectural millwork and custom casework.",
        },
        {
            "NoticeId": "irrelevant-1",
            "Title": "Network support services",
            "Sol#": "SOL-2",
            "Department/Ind.Agency": "TEST AGENCY",
            "Sub-Tier": "",
            "PostedDate": "2026-11-01 12:00:00",
            "Type": "Solicitation",
            "BaseType": "Solicitation",
            "SetASideCode": "",
            "SetASide": "",
            "ResponseDeadLine": "2026-11-20T12:00:00-08:00",
            "NaicsCode": "541519",
            "ClassificationCode": "DA10",
            "PopCity": "Los Angeles",
            "PopState": "CA",
            "PopZip": "90012",
            "Active": "Yes",
            "Office": "TEST OFFICE",
            "AwardNumber": "",
            "AwardDate": "",
            "Award$": "",
            "AdditionalInfoLink": "",
            "Link": "https://sam.gov/workspace/contract/opp/irrelevant-1/view",
            "Description": "IT network operations and support.",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_sam_full_csv_import_streams_scores_and_maps_fields(tmp_path: Path):
    path = tmp_path / "ContractOpportunitiesFullCSV.csv"
    _write_csv(path)

    payload = import_sam_opportunity_csv(
        path,
        preferred_states={"CA"},
        minimum_score=20,
    )

    assert payload["rows_scanned"] == 2
    assert payload["total_normalized"] == 2
    assert payload["total_shown"] == 1
    row = payload["opportunities"][0]
    opp = row["opportunity"]
    assert opp["source"] == "sam.gov CSV"
    assert opp["external_id"] == "relevant-1"
    assert opp["naics_code"] == "337212"
    assert opp["city"] == "Los Angeles"
    assert opp["state"] == "CA"
    assert opp["url"].endswith("/relevant-1/view")
    assert opp["metadata"]["solicitation_number"] == "SOL-1"
    assert row["score"] >= 20


def test_sam_csv_rejects_unrelated_schema(tmp_path: Path):
    path = tmp_path / "other.csv"
    path.write_text("name,value\na,b\n", encoding="utf-8")

    try:
        import_sam_opportunity_csv(path)
    except ValueError as exc:
        assert "SAM.gov Contract Opportunities full export" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unrelated CSV schema")
