# Auto Bid Builder

A bid-assistance system for commercial architectural millwork and custom fabrication.

The goal is to turn a contractor/architect bid package into a traceable millwork scope, takeoff, risk review, estimate, and proposal draft without losing the drawing/spec evidence behind each decision.

## Intended workflow

1. **Ingest** bid-set PDFs, specifications, addenda, fixture schedules, finish schedules, and responsibility schedules.
2. **Classify** project metadata, relevant sheets, divisions, vendor-furnished vs GC/subcontractor responsibilities, and millwork scope.
3. **Extract** bid items with drawing/spec references, dimensions, materials, finishes, hardware, installation responsibility, custom/modification flags, and sustainability requirements.
4. **Cross-check** plans, schedules, elevations, details, specs, addenda, and responsibility tables for conflicts or omissions.
5. **Take off** quantities and convert custom work into fabrication/installation operations.
6. **Estimate** material, waste, hardware, CNC time, bench labor, finishing, assembly, packaging, freight, field labor, PM/engineering, subcontractors, overhead, contingency, and margin.
7. **Generate** scope, alternates, allowances, qualifications, exclusions, RFIs, and a proposal draft.
8. **Learn** from awarded jobs and actual production/material/labor history so future estimates reflect JTI's real performance rather than generic unit pricing.

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
- Human estimator approval is required before a bid is considered final.

## Repository data policy

Real bid packages may contain copyrighted drawings, customer information, vendor contacts, pricing, and other non-public data. Do **not** commit raw project PDFs or private estimates to this public repository. Keep project inputs/outputs in ignored local directories or another approved private store.

## Planned layout

```text
auto_bid_builder/
  ingest/
  extract/
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

The first implementation milestone is:

> **Bid-set PDF in -> evidence-backed millwork scope + takeoff review package out.**

Pricing automation comes after the extraction/takeoff layer is reliable enough to audit.