# Auto Bid Builder

A bid-assistance system for commercial architectural millwork and custom fabrication.

The goal is to turn a contractor/architect bid package into a traceable millwork scope, takeoff, risk review, estimate, and proposal draft without losing the drawing/spec evidence behind each decision.

## Intended workflow

1. **Ingest** bid-set PDFs, specifications, addenda, fixture schedules, finish schedules, responsibility schedules, CAD packages, and historical quotes.
2. **Classify** project metadata, relevant sheets, divisions, vendor-furnished vs GC/subcontractor responsibilities, and millwork scope.
3. **Extract** bid items with drawing/spec references, dimensions, materials, finishes, hardware, installation responsibility, custom/modification flags, and sustainability requirements.
4. **Cross-check** plans, schedules, elevations, details, specs, addenda, responsibility tables, RFIs, and later bulletins for conflicts or omissions.
5. **Take off** quantities and convert custom work into fabrication/installation operations.
6. **Estimate** material, waste, hardware, CNC time, bench labor, finishing, assembly, packaging, freight, field labor, PM/engineering, subcontractors, overhead, contingency, and margin.
7. **Generate** scope, alternates, allowances, qualifications, exclusions, RFIs, and a JTI-style quotation draft.
8. **Track revisions** after bid so bulletins/RFIs can be compared against the quoted scope for change-order impact.
9. **Learn** from awarded jobs and actual production/material/labor history so future estimates reflect JTI's real performance rather than generic unit pricing.

## V1 - usable now

V1 is the evidence and revision-audit foundation. It does **not** invent prices. It is designed to make the estimator faster while keeping every decision reviewable.

Install locally:

```bash
python -m pip install -e .
```

Parse a JTI quotation PDF and verify the displayed math:

```bash
auto-bid-builder parse-quote "119236 Orrick Quote.pdf" -o quote.json
```

Rank millwork-relevant pages in a drawing package or folder:

```bash
auto-bid-builder scan ./data/input -o bid_scan.json
```

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

The V1 quote parser was tested against JTI quote 119236 and parsed all 21 displayed line items. The calculated line total matched the displayed quote total of $338,415.00. The source quote and customer pricing are intentionally not stored in this public repository.

The revision-audit workflow was also exercised against the Orrick bid-basis sheets and Bulletin 2. It detected estimator-relevant A8.00 changes including RFI references, a new cabinet-notch signal, and changed dimensions, then conservatively mapped that sheet-level change back to the six quoted A8.00 line items for human review. This is intentionally a review flag, not an automatic change-order conclusion.

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
- Human estimator approval is required before a bid is considered final.

## Current implementation

- Fast PDF sheet/text extraction for drawing packages and compiled bulletins.
- Package inventory with ZIP/CAD awareness.
- Conservative text signal extraction for millworker responsibility, custom work, field verification, materials, and dimensions.
- JTI-style quote PDF parsing into numbered scope lines with quantity, sell-each, tax-each, amount, sheet references, and elevation references.
- Quote arithmetic validation at line and document total level.
- Millwork page relevance scan.
- Revision-impact extraction for finish codes, RFIs, dimensions, VIF/coordination notes, filler/notch changes, lighting, blocking, millwork, and other estimator-relevant signals.
- Mapping from revised drawing sheets back to JTI quote lines that explicitly cite those sheets.
- JSON and Markdown estimator-review outputs.
- Regression tests use synthetic examples only; customer drawings, quotes, and pricing stay outside the public repository.

## Repository data policy

Real bid packages may contain copyrighted drawings, customer information, vendor contacts, pricing, and other non-public data. Do **not** commit raw project PDFs or private estimates to this public repository. Keep project inputs/outputs in ignored local directories or another approved private store.

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

The next major milestone is automatic **scope-item construction and takeoff** from bid documents, followed by pricing calibration from JTI historical internal estimates/actual job costs.

Pricing automation will use JTI history rather than silently substituting generic construction unit prices.
