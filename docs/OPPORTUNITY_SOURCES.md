# Construction opportunity sources

Auto Bid Builder treats lead discovery as a provider layer. Every source is normalized to the same `Opportunity` model before JTI-fit triage, document intake, scope extraction, or estimating.

## Public / no-login sources enabled now

The local opportunity sync can pull sources that expose useful public opportunity pages without requiring JTI credentials. Current built-in adapters are:

- **California Construction Authority** public Bid/RFP/RFQ page.
- **California DGS RESD** current construction/real-estate solicitations page.
- **Custom RSS/Atom feeds** entered in Settings.

The California Construction Authority page is public and lists current Invitations to Bid, RFPs, and quotation requests. Some individual packets are hosted on Public Purchase and require the provider's free vendor registration/login; Auto Bid Builder does not bypass that boundary.

Public sources are isolated from one another. If a site blocks automated requests or changes its markup, the sync records a source-specific error and continues processing other sources.

Run all enabled sources:

```bash
auto-bid-sync -o opportunities.json
```

Open the local provider/settings page:

```bash
auto-bid-settings --port 8765
```

Then open `http://127.0.0.1:8765/settings`.

The settings page controls preferred states, lookback period, minimum JTI triage score, public source enable/disable state, custom RSS/Atom feeds, and credential slots for commercial/API-backed providers. Secrets are kept outside Git in the operating-system credential store when available; `ABB_*` environment variables are also supported as read-only overrides.

## Credentialed provider roadmap

### Autodesk BuildingConnected / Bid Board Pro

Primary target for JTI's private commercial invitations-to-bid workflow.

Official Autodesk documentation states that the BuildingConnected API exposes opportunity and bidding data from Bid Board Pro / BuildingConnected Pro. Opportunity access requires a Bid Board Pro subscription and uses APS three-legged OAuth. BuildingConnected also supports webhooks such as `opportunity.created` and `opportunity.status.updated`, which makes it a strong fit for real-time intake.

Integration target:

1. OAuth user authorization.
2. Pull existing opportunities into the normalized model.
3. Subscribe to opportunity-created / status-changed webhooks.
4. Pull accessible bid attachments.
5. Run JTI fit triage.
6. For estimator-approved leads, ingest plans/specs into the existing bid-document pipeline.

Do not scrape BuildingConnected pages when API access is available.

### Dodge Construction Network API

Strong candidate for proactive lead discovery rather than only incoming ITBs. Dodge advertises REST/OAuth access to projects, firms/contacts, and project documents, with filters such as geography, project type, stage, valuation, trade, spec division, and bid date. Access is commercial and must be provisioned through Dodge.

### PlanHub Projects API

PlanHub advertises API access to planning-stage and bidding-stage project data and supports CRM/estimating/ERP integrations. Endpoint access depends on the PlanHub package purchased.

### ConstructConnect / SmartBid

ConstructConnect operates an external API portal, and SmartBid exposes authenticated API functionality. These are useful if JTI already has a subscription. Provider-specific adapters should be implemented only from the documentation available to JTI's account.

### SAM.gov Contract Opportunities API

SAM.gov is implemented as a live authenticated provider. It requires a SAM.gov public API key and a posted-date range. Auto Bid Builder can search repeated title/state/NAICS filters, normalize records, deduplicate results, and create a JTI estimator review queue.

Once a SAM.gov key is entered in Settings and that source is enabled, `auto-bid-sync` includes it automatically.

The older direct command remains available:

```bash
auto-bid-builder find-opportunities \
  --provider sam \
  --state CA \
  --state NV \
  --preferred-state CA \
  --preferred-state NV \
  --hydrate-descriptions \
  --min-score 20 \
  -o ./data/output/opportunities.json
```

## Normalized pipeline

```text
Public bid page / RSS / provider API / webhook
        |
        v
Normalized Opportunity
        |
        v
JTI fit triage
        |
        +--> low signal -> archive / manual review
        |
        v
Estimator shortlist
        |
        v
Authorized document download
        |
        v
Bid package scan / scope extraction / risk review
        |
        v
Takeoff + historically calibrated estimate
        |
        v
Estimator approval
        |
        v
JTI quote draft
```

## JTI-fit scoring

The initial score is deliberately transparent and editable. It looks for evidence such as architectural millwork, architectural woodwork, casework, cabinetry, custom/retail fixtures, cash wraps/backwraps, reception desks, wall panels, veneer, laminate, FSC, finish carpentry, and common millwork specification divisions. Availability of bid documents and a due date also add small review signals.

The score is **not** a bid/no-bid decision. It is only a queueing mechanism so an estimator sees likely JTI work first. Historical wins, losses, final margins, actual hours, and customer/GC relationships should eventually calibrate the weights.

## Security / data policy

- Keep provider secrets in the OS credential store or environment variables, never in Git.
- Use provider APIs and authorized document links; do not bypass authentication or subscription controls.
- Do not commit customer opportunity payloads, plan sets, bid documents, contacts, or pricing to the public repository.
- Store provider IDs so opportunities can be updated rather than duplicated.
- Preserve source evidence and timestamps for every imported opportunity.
