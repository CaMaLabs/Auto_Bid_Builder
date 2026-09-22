from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from auto_bid_builder.settings import AppSettings, SecretStore, cache_path, load_settings
from .models import Opportunity
from .providers.public import fetch_cca_opportunities, fetch_dgs_resd_opportunities, fetch_rss_atom
from .providers.sam import JTI_NAICS_CODES, search_sam_opportunities
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
    source_stats: list[dict[str, object]] = []

    for provider in settings.providers:
        sam_key: str | None = None
        auto_enabled_from_credential = False
        if provider.kind == "sam":
            sam_key = secret_store.get(provider.id, "api_key")
            # Hand-holding behavior: entering a SAM API key is a strong indication
            # that the user wants SAM searched. Older builds saved the key while
            # leaving the provider's default disabled flag untouched, making the UI
            # appear to accept the credential while silently skipping SAM.
            if sam_key and not provider.enabled:
                auto_enabled_from_credential = True

        if not provider.enabled and not auto_enabled_from_credential:
            continue

        try:
            if provider.kind == "cca_public":
                rows = fetch_cca_opportunities(provider.base_url) if provider.base_url else fetch_cca_opportunities()
                opportunities.extend(rows)
                used_sources.append(provider.label)
                source_stats.append({"source": provider.label, "provider_id": provider.id, "fetched": len(rows)})
            elif provider.kind == "ca_dgs_resd":
                rows = fetch_dgs_resd_opportunities(provider.base_url) if provider.base_url else fetch_dgs_resd_opportunities()
                opportunities.extend(rows)
                used_sources.append(provider.label)
                source_stats.append({"source": provider.label, "provider_id": provider.id, "fetched": len(rows)})
            elif provider.kind == "rss":
                if provider.feed_url:
                    rows = fetch_rss_atom(provider.feed_url, source_name=provider.label)
                    opportunities.extend(rows)
                    used_sources.append(provider.label)
                    source_stats.append({"source": provider.label, "provider_id": provider.id, "fetched": len(rows)})
            elif provider.kind == "sam":
                api_key = sam_key or secret_store.get(provider.id, "api_key")
                if not api_key:
                    errors.append({"source": provider.label, "error": "enabled but no API key is configured"})
                    continue
                today = date.today()
                start = today - timedelta(days=settings.lookback_days)
                rows = search_sam_opportunities(
                    api_key=api_key,
                    posted_from=start.strftime("%m/%d/%Y"),
                    posted_to=today.strftime("%m/%d/%Y"),
                    titles=("millwork", "casework", "cabinetry", "architectural woodwork", "finish carpentry"),
                    states=tuple(settings.preferred_states),
                    naics_codes=JTI_NAICS_CODES,
                    hydrate_descriptions=True,
                )
                opportunities.extend(rows)
                used_sources.append(provider.label)
                source_stats.append(
                    {
                        "source": provider.label,
                        "provider_id": provider.id,
                        "fetched": len(rows),
                        "auto_enabled_from_saved_key": auto_enabled_from_credential,
                        "states": list(settings.preferred_states),
                        "lookback_days": settings.lookback_days,
                    }
                )
            else:
                errors.append({"source": provider.label, "error": "adapter not implemented yet; settings are saved for future use"})
        except Exception as exc:
            errors.append({"source": provider.label, "error": f"{type(exc).__name__}: {exc}"})

    normalized = _dedupe(opportunities)
    scored = score_opportunities(normalized, preferred_states=set(settings.preferred_states))
    shown = [row for row in scored if row.score >= settings.minimum_score]

    shown_by_source: dict[str, int] = {}
    normalized_by_source: dict[str, int] = {}
    for opp in normalized:
        normalized_by_source[opp.source] = normalized_by_source.get(opp.source, 0) + 1
    for row in shown:
        source = row.opportunity.source
        shown_by_source[source] = shown_by_source.get(source, 0) + 1
    for stat in source_stats:
        if stat.get("provider_id") == "sam":
            stat["normalized"] = normalized_by_source.get("sam.gov", 0)
            stat["shown"] = shown_by_source.get("sam.gov", 0)

    return {
        "sources": used_sources,
        "source_stats": source_stats,
        "errors": errors,
        "total_normalized": len(normalized),
        "minimum_score": settings.minimum_score,
        "total_shown": len(shown),
        "opportunities": [row.to_dict() for row in shown],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pull configured bid opportunities and rank them for JTI review")
    parser.add_argument("-o", "--output", help="JSON output path; defaults to the local opportunity cache")
    args = parser.parse_args(argv)
    result = sync_opportunities(load_settings())
    path = Path(args.output) if args.output else cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(path)
    if result["errors"]:
        for row in result["errors"]:
            print(f"WARNING {row['source']}: {row['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
