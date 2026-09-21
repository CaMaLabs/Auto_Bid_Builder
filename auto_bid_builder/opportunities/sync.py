from __future__ import annotations

from datetime import date, timedelta

from auto_bid_builder.settings import AppSettings, SecretStore
from .models import Opportunity
from .providers.public import fetch_cca_opportunities, fetch_dgs_resd_opportunities, fetch_rss_atom
from .providers.sam import search_sam_opportunities
from .score import score_opportunities


def _dedupe(opportunities: list[Opportunity]) -> list[Opportunity]:
    seen: set[tuple[str, str]] = set()
    out: list[Opportunity] = []
    for opp in opportunities:
        key = (opp.source.lower(), (opp.external_id or opp.title).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(opp)
    return out


def sync_opportunities(settings: AppSettings, secret_store: SecretStore | None = None) -> dict:
    secret_store = secret_store or SecretStore()
    opportunities: list[Opportunity] = []
    errors: list[dict[str, str]] = []
    used_sources: list[str] = []

    for provider in settings.providers:
        if not provider.enabled:
            continue
        try:
            if provider.kind == "cca_public":
                opportunities.extend(fetch_cca_opportunities(provider.base_url or None))
                used_sources.append(provider.label)
            elif provider.kind == "ca_dgs_resd":
                opportunities.extend(fetch_dgs_resd_opportunities(provider.base_url or None))
                used_sources.append(provider.label)
            elif provider.kind == "rss":
                if provider.feed_url:
                    opportunities.extend(fetch_rss_atom(provider.feed_url, source_name=provider.label))
                    used_sources.append(provider.label)
            elif provider.kind == "sam":
                api_key = secret_store.get(provider.id, "api_key")
                if not api_key:
                    errors.append({"source": provider.label, "error": "enabled but no API key is configured"})
                    continue
                today = date.today()
                start = today - timedelta(days=settings.lookback_days)
                opportunities.extend(
                    search_sam_opportunities(
                        api_key=api_key,
                        posted_from=start.strftime("%m/%d/%Y"),
                        posted_to=today.strftime("%m/%d/%Y"),
                        titles=("millwork", "casework", "cabinetry", "architectural woodwork", "finish carpentry"),
                        states=tuple(settings.preferred_states),
                        hydrate_descriptions=False,
                    )
                )
                used_sources.append(provider.label)
            else:
                errors.append({"source": provider.label, "error": "adapter not implemented yet; settings are saved for future use"})
        except Exception as exc:
            errors.append({"source": provider.label, "error": f"{type(exc).__name__}: {exc}"})

    normalized = _dedupe(opportunities)
    scored = score_opportunities(normalized, preferred_states=set(settings.preferred_states))
    shown = [row for row in scored if row.score >= settings.minimum_score]
    return {
        "sources": used_sources,
        "errors": errors,
        "total_normalized": len(normalized),
        "minimum_score": settings.minimum_score,
        "total_shown": len(shown),
        "opportunities": [row.to_dict() for row in shown],
    }
