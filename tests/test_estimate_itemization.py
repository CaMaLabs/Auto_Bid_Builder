from pathlib import Path
import json

from auto_bid_builder.estimate.draft import create_estimate_from_workspace


def test_estimate_preserves_scope_itemization_by_reference(tmp_path: Path):
    root = tmp_path / "bid"
    (root / "output").mkdir(parents=True)
    payload = {
        "pages": [
            {
                "source": "plans.pdf",
                "page": 8,
                "sheet": "A8.00",
                "relevance_score": 14,
                "scope_terms": ["casework", "cabinetry"],
                "signals": [],
            },
            {
                "source": "plans.pdf",
                "page": 9,
                "sheet": "A8.10",
                "relevance_score": 12,
                "scope_terms": ["casework"],
                "signals": [],
            },
            {
                "source": "plans.pdf",
                "page": 10,
                "sheet": "A8.20",
                "relevance_score": 10,
                "scope_terms": ["countertop", "wood veneer"],
                "signals": [],
            },
        ]
    }
    (root / "output" / "bid_review.json").write_text(json.dumps(payload), encoding="utf-8")

    draft = create_estimate_from_workspace(root, "Synthetic Itemized Bid")

    # casework/cabinetry synonyms on one sheet become one row, but separate
    # sheets and separate scope types remain separately reviewable/priced.
    assert len(draft.lines) == 4
    descriptions = [line.description for line in draft.lines]
    assert "Casework / cabinetry (A8.00)" in descriptions
    assert "Casework / cabinetry (A8.10)" in descriptions
    assert "Countertops / worktops (A8.20)" in descriptions
    assert "Wood veneer (A8.20)" in descriptions
    assert all(len(line.source_refs) == 1 for line in draft.lines)
    assert all(line.material_cost > 0 for line in draft.lines)
    assert not any("allowance — detected across" in line.description.lower() for line in draft.lines)
