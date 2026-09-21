# Construction opportunity sources

Auto Bid Builder treats lead discovery as a provider layer. Every source is normalized to the same `Opportunity` model before JTI-fit triage, document intake, scope extraction, or estimating.

## Recommended provider order

### 1. Autodesk BuildingConnected / Bid Board Pro

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

### 2. Dodge Construction Network API

Strong candidate for proactive lead discovery rather than only incoming ITBs. Dodge advertises REST/OAuth access to projects, firms/contacts, and project documents, with filters such as geography, project type, stage, valuation, trade, spec division, and bid date. Access is commercial and must be provisioned through Dodge.

This is potentially the best source for finding projects JTI was not already invited to.

### 3. PlanHub Projects API

PlanHub advertises API access to planning-stage and bidding-stage project data and supports CRM/estimating/ERP integrations. Endpoint access depends on the PlanHub package purchased. Add this adapter after JTI confirms account/API access and provides the provider documentation/credentials.

### 4. ConstructConnect / SmartBid

ConstructConnect operates an external API portal, and SmartBid exposes an authenticated Web API help endpoint. These are useful if JTI already has a subscription. Provider-specific schemas should be implemented only from the documentation available to JTI's account.

### 5. SAM.gov public Contract Opportunities API

This is the first live provider implemented in the repository because its public API is documented and testable without a commercial construction-data subscription. It is most useful for federal/public-sector opportunities and as a proving ground for the provider architecture.

The API requires a SAM.gov public API key and a posted-date range. Auto Bid Builder can search repeated title/state/NAICS filters, normalize records, optionally fetch opportunity descriptions, deduplicate results, and create a JTI estimator review queue.

Example:

```bash
export SAM_GOV_API_KEY="..."

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

The companion Markdown review file is written beside the JSON output.

## Normalized pipeline

```text
Provider API / webhook
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

- Keep provider secrets in environment variables or an approved secret store, never in Git.
- Use provider APIs and authorized document links; do not bypass authentication or subscription controls.
- Do not commit customer opportunity payloads, plan sets, bid documents, contacts, or pricing to the public repository.
- Store provider IDs so opportunities can be updated rather than duplicated.
- Preserve source evidence and timestamps for every imported opportunity.
