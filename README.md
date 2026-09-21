# Auto Bid Builder

A bid-assistance system for commercial architectural millwork and custom fabrication.

The goal is to turn a contractor/architect bid package into a traceable millwork scope, takeoff, risk review, estimate, and proposal draft without losing the drawing/spec evidence behind each decision.

## Intended workflow

1. **Ingest** bid-set PDFs, specifications, addenda, fixture schedules, finish schedules, responsibility schedules, CAD packages, historical quotes, submittals, RFIs, ASKs, field measurements, shop drawings, historical cost-detail estimates, and purchasing/job-cost evidence.
2. **Classify** project metadata, relevant sheets, divisions, vendor-furnished vs GC/subcontractor responsibilities, and millwork scope.
3. **Extract** bid items with drawing/spec references, dimensions, materials, finishes, hardware, installation responsibility, custom/modification flags, and sustainability requirements.
4. **Cross-check** plans, schedules, elevations, details, specs, addenda, responsibility tables, RFIs, ASKs, field measurements, shop drawings, and later bulletins for conflicts or omissions.
5. **Take off** quantities and convert custom work into fabrication/installation operations.
6. **Estimate** material, waste, hardware, CNC time, bench labor, finishing, assembly, packaging, freight, field labor, PM/engineering, subcontractors, overhead, contingency, and margin.
7. **Generate** scope, alternates, allowances, qualifications, exclusions, RFIs, and a JTI-style quotation draft.
8. **Track revisions** after bid so bulletins/RFIs/ASKs/submittal comments can be compared against the quoted scope for change-order impact.
9. **Learn** from awarded jobs and actual production/material/labor history so future estimates reflect JTI's real performance rather than generic unit pricing.

## V1 - usable now

V1 is the evidence, revision-audit, and historical-calibration foundation. It does **not** invent prices. It is designed to make the estimator faster while keeping every decision reviewable.

Install locally:

```bash
python -m pip install -e .
```

Parse a JTI quotation PDF and verify the displayed math:

```bash
auto-bid-builder parse-quote "119236 Orrick Quote.pdf" -o quote.json
```

Parse a historical JTI cost-detail estimate. This reconstructs each line's labor from the displayed labor-category hours/rates, validates sell-each and extended totals, and infers the pricing relationships actually present in that document rather than hard-coding a company-wide rate or markup:

```bash
auto-bid-builder parse-cost-detail "118331 cost detail.pdf" -o cost_detail.json
```

A historical cost detail is treated as **estimate/pricing evidence**, not automatically as realized job cost. In particular, projected hours, displayed labor dollars, material allowances and markups must remain distinct from later actual payroll, purchasing, subcontractor and rework data.

Rank millwork-relevant pages in a drawing package or folder:

```bash
auto-bid-builder scan ./data/input -o bid_scan.json
```

Audit a live-project document folder and surface lifecycle state such as field measurements, revised shop drawings, RFIs/ASKs, submittal status, finish approvals, and coordination dependencies:

```bash
auto-bid-builder project-audit ./data/input/project_docs -o project_audit.json
```

This also writes `project_audit.md` unless another Markdown path is supplied with `--markdown`.

Normalize historical vendor purchases to CSV, then summarize the **known** purchasing evidence for an awarded job. Supplying the original quote adds an evidence-coverage ratio; it is deliberately not labeled as margin because purchasing packets may be incomplete and do not include labor/overhead automatically.

```bash
auto-bid-builder procurement-summary ./data/private/job_119236_purchases.csv \
  --quote "119236 Orrick Quote.pdf" \
  -o ./data/output/job_119236_procurement.json
```

The normalized CSV accepts these columns (additional columns are ignored):

```text
source,vendor,date,po,document_number,document_kind,item,description,quantity,uom,unit_cost,line_amount,freight,tax,document_total,priced
```

A single vendor document may occupy multiple rows. Document totals/freight/tax may be repeated on those rows; the summarizer counts each document-level value once and reports displayed-total vs component reconciliation deltas when enough evidence exists.

Compare a later compiled bulletin against the bid-basis single-sheet PDFs and map estimator-relevant changes back to quoted line items:

```bash
auto-bid-builder revision-audit \
  --quote "119236 Orrick Quote.pdf" \
  --baseline-dir ./data/input/bid_basis \
  --revision "Bulletin 2.pdf" \
  --output-dir ./data/output/orrick_bulletin_2
```

The revision audit writes:

- `quote.json` - structured JTI quote lines and arithmetic validation
- `revision_audit.json` - machine-readable sheet and quote-line impacts
- `revision_audit.md` - estimator review queue

### Real-world V1 validation

The V1 quote parser was tested against a real JTI quotation and parsed all displayed line items while reproducing the displayed total from the individual line amounts. Source customer documents and private project files are intentionally not stored in this public repository.

The historical cost-detail parser was shaped against an awarded JTI job whose internal estimate contained per-item labor-category hours/rates, material allowance, material markup, manual add, tax, unit sell and extended sell. The parser reconstructs those displayed calculations and infers the document's rate/markup relationships without publishing or hard-coding private historical pricing.

The revision-audit workflow was exercised against a real bid-basis drawing set and later bulletin. It detected estimator-relevant sheet changes including RFI references, cabinet/fabrication changes, and changed dimensions, then conservatively mapped those sheet-level changes back to quoted line items for human review. This is intentionally a review flag, not an automatic change-order conclusion.

The project-lifecycle audit has also been shaped against real field-measure packages, original and revised JTI shop drawings, ASK/RFI documents, architectural millwork markups, and reviewed material/product submittals. Important distinction: an external trade's approved product submittal can be a **coordination input** without becoming JTI furnish/install scope.

Historical purchasing packets from awarded work are treated as **cost evidence**, including priced sales orders/invoices as well as unpriced packing lists, manifests, and delivery tickets. The system preserves unpriced evidence rather than dropping it and refuses to treat the visible purchase total as complete job cost unless coverage has independently been established.

## Scope focus

- Custom cabinetry and casework
- Back-of-house millwork and fixtures
- High-end retail/storefront millwork
- Wall panels, feature elements, counters, shelving, custom fixtures
- FSC / chain-of-custody and other sustainability documentation
- Highly customized one-off work

## Design principles

- Every extracted bid item should retain **evidence**: source file, sheet/page, drawing/detail reference, and confidence.
- Never silently resolve conflicting documents. Flag them for estimator review or RFI.
- Separate **furnished by**, **installed by**, and **blocking/rough-in by** responsibilities.
- Treat custom/modified fixture codes and vendor shop-drawing dependencies as cost/risk signals.
- Keep scope and proposal generation tied to the same structured estimate so wording and price do not drift apart.
- Compare later bulletins and RFIs against the original bid basis using estimator-relevant signals rather than relying only on brittle PDF line diffs.
- Treat field-measure photos/handwritten dimensions as visual evidence requiring review when no reliable text layer is available.
- Treat `REVISE AND RESUBMIT` and similar review states as unresolved fabrication inputs, not as silently approved finishes.
- Keep other-trade product approvals separate from JTI cost responsibility while still tracking their dimensional/coordination impact on millwork.
- Keep historical **estimated** cost-detail data separate from later **actual** job-cost evidence.
- Keep historical vendor purchasing evidence separate from a complete job-cost conclusion; unpriced tickets, missing invoices, labor, outsourcing, install, freight/tax, overhead, and rework can materially change actual cost.
- Contract/payment terms are project-specific; a quote/database terms code must not silently override negotiated subcontract terms.
- Human estimator approval is required before a bid is considered final.

## Current implementation

- Fast PDF sheet/text extraction for drawing packages and compiled bulletins.
- Package inventory with ZIP/CAD awareness.
- Conservative text signal extraction for millworker responsibility, custom work, field verification, materials, and dimensions.
- JTI-style quote PDF parsing into numbered scope lines with quantity, sell-each, tax-each, amount, sheet references, and elevation references.
- Historical JTI cost-detail parsing with labor-category hours/rates, materials, markup, manual adds, tax, unit sell, extended sell, aggregate validation, and inferred document-level calibration.
- Quote and cost-detail arithmetic validation at line and document total level.
- Millwork page relevance scan.
- Project-lifecycle document classification for field measures, shop drawings/revisions, RFIs, ASKs, bulletins, quotes, and submittals.
- Extraction of spec section, responsible contractor, finish codes, explicit review actions, and unresolved submittal flags.
- Historical procurement ledger normalization/summarization with priced and unpriced document coverage, vendor totals, reconciliation deltas, and optional quote-coverage calculation.
- Revision-impact extraction for finish codes, RFIs, dimensions, VIF/coordination notes, filler/notch changes, lighting, blocking, millwork, and other estimator-relevant signals.
- Mapping from revised drawing sheets back to JTI quote lines that explicitly cite those sheets.
- JSON and Markdown estimator-review outputs.
- Regression tests use synthetic examples only; customer drawings, quotes, cost details, purchasing records, and pricing stay outside the public repository.

## Repository data policy

Real bid packages may contain copyrighted drawings, customer information, vendor contacts, pricing, and other non-public data. Do **not** commit raw project PDFs or private estimates/purchasing records to this public repository. Keep project inputs/outputs in ignored local directories or another approved private store.

## Planned layout

```text
auto_bid_builder/
  ingest/
  extract/
  analysis/
  quote/
  revisions/
  takeoff/
  estimate/
  proposal/
  validation/
schemas/
docs/
tests/
data/
  input/      # ignored
  output/     # ignored
  private/    # ignored
```

The next major milestone is automatic **scope-item construction and takeoff** from bid documents, then linking those scope items to historical labor/material patterns and later actual job-cost evidence.

Pricing automation will use JTI history rather than silently substituting generic construction unit prices.
