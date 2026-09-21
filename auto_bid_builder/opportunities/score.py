from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import Opportunity


# These are triage signals, not automatic bid/no-bid decisions.  Weights are kept
# explicit so JTI can tune them from historical wins/losses later.
DEFAULT_SIGNALS: tuple[tuple[str, float], ...] = (
    ("architectural millwork", 36.0),
    ("architectural woodwork", 36.0),
    ("millwork", 30.0),
    ("casework", 28.0),
    ("cabinetry", 26.0),
    ("cabinets", 22.0),
    ("custom fixture", 24.0),
    ("retail fixture", 24.0),
    ("store fixture", 22.0),
    ("cash wrap", 22.0),
    ("cashwrap", 22.0),
    ("backwrap", 22.0),
    ("reception desk", 20.0),
    ("wall panel", 16.0),
    ("wood veneer", 15.0),
    ("veneer", 10.0),
    ("plastic laminate", 12.0),
    ("laminate", 8.0),
    ("solid surface", 8.0),
    ("fsc", 8.0),
    ("finish carpentry", 18.0),
    ("064000", 32.0),
    ("06 40 00", 32.0),
    ("064100", 30.0),
    ("06 41 00", 30.0),
    ("123200", 24.0),
    ("12 32 00", 24.0),
)

DEFAULT_NEGATIVE_SIGNALS: tuple[tuple[str, float], ...] = (
    ("residential tract", -18.0),
    ("rough carpentry only", -20.0),
    ("roofing", -8.0),
    ("site concrete", -8.0),
    ("asphalt", -8.0),
)


@dataclass(frozen=True)
class OpportunityScore:
    opportunity: Opportunity
    score: float
    tier: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "opportunity": self.opportunity.to_dict(),
            "score": self.score,
            "tier": self.tier,
            "reasons": list(self.reasons),
        }


def score_opportunity(
    opportunity: Opportunity,
    *,
    preferred_states: set[str] | None = None,
    positive_signals: tuple[tuple[str, float], ...] = DEFAULT_SIGNALS,
    negative_signals: tuple[tuple[str, float], ...] = DEFAULT_NEGATIVE_SIGNALS,
) -> OpportunityScore:
    text = opportunity.search_text
    score = 0.0
    reasons: list[str] = []

    for phrase, weight in positive_signals:
        if phrase in text:
            score += weight
            reasons.append(f"+{weight:g} matched '{phrase}'")

    for phrase, weight in negative_signals:
        if phrase in text:
            score += weight
            reasons.append(f"{weight:g} matched '{phrase}'")

    if opportunity.attachments:
        score += 8.0
        reasons.append("+8 bid documents/attachments available")

    if opportunity.bid_due_date:
        score += 3.0
        reasons.append("+3 bid due date supplied")

    if preferred_states and opportunity.state:
        state = opportunity.state.upper()
        if state in {x.upper() for x in preferred_states}:
            score += 8.0
            reasons.append(f"+8 preferred state {state}")

    score = round(score, 2)
    if score >= 45:
        tier = "strong_review"
    elif score >= 20:
        tier = "possible_review"
    else:
        tier = "low_signal"

    return OpportunityScore(opportunity=opportunity, score=score, tier=tier, reasons=tuple(reasons))


def score_opportunities(
    opportunities: list[Opportunity], *, preferred_states: set[str] | None = None
) -> list[OpportunityScore]:
    rows = [score_opportunity(x, preferred_states=preferred_states) for x in opportunities]
    rows.sort(key=lambda x: (-x.score, x.opportunity.bid_due_date or "9999", x.opportunity.title.lower()))
    return rows
