from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Opportunity:
    """Provider-neutral construction bid opportunity.

    The goal is to keep provider-specific payloads out of the estimating pipeline.  Any
    lead source (BuildingConnected, Dodge, PlanHub, SAM.gov, etc.) should normalize
    into this shape before JTI fit scoring or document review begins.
    """

    source: str
    external_id: str
    title: str
    description: str = ""
    organization: str | None = None
    posted_date: str | None = None
    bid_due_date: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    naics_code: str | None = None
    classification_code: str | None = None
    url: str | None = None
    attachments: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        values = [
            self.title,
            self.description,
            self.organization or "",
            self.naics_code or "",
            self.classification_code or "",
            " ".join(str(x) for x in self.metadata.get("keywords", ())),
        ]
        return " ".join(values).lower()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
