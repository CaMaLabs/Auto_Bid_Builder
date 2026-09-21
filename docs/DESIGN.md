# Design Notes

## Why the first milestone is scope extraction

Architectural bid packages frequently mix responsibility across fixture schedules, finish schedules, elevations, details, specifications, electrical drawings, and vendor shop-drawing references. Pricing directly from raw text is unsafe because the same item may be furnished by one party, installed by another, require blocking by a third, and depend on a later vendor submittal.

Auto Bid Builder therefore separates four stages:

1. **Evidence extraction** — identify what the documents actually say.
2. **Scope normalization** — turn drawing/spec language into structured bid items and responsibilities.
3. **Estimator review** — resolve ambiguities, inclusions, exclusions, alternates, allowances, and RFIs.
4. **Pricing/proposal** — cost only the reviewed scope and generate proposal language from that same data.

## Evidence model

Every important conclusion should point back to:

- source document
- page and, when available, sheet number
- detail/elevation reference
- note or table context
- extraction confidence

Conflicting evidence is retained rather than overwritten.

## Responsibility model

Responsibility is not a single field. Track separately:

- furnished by
- installed by
- blocking/backing by
- electrical/plumbing/low-voltage rough-in by
- shop drawings/submittals by
- field verification responsibility

This is especially important for retail fixture packages where owner/vendor-supplied assemblies can still create substantial installation, coordination, blocking, finish, electrical, and field-labor scope.

## Extraction targets

Prioritize these sheets/sections when present:

- cover/index and issue history
- responsibility schedule
- fixture/equipment schedule
- finish schedule and finish plan
- fixture plan
- FOH/BOH elevations
- enlarged plans
- storefront plans/elevations/sections
- typical millwork details
- architectural specifications
- sustainability/FSC requirements
- electrical/plumbing drawings where they interface with millwork
- addenda and revision clouds

## Custom-work signals

The parser should increase review priority for:

- explicit `CUSTOM` or `MODIFIED` notes
- special fixture-code conventions indicating customization
- dimensions marked `VIF`, `VARIES`, `HOLD`, or similar
- references to vendor shop drawings not present in the package
- field-verified dimensions
- integrated lighting, power, data, safes, appliances, plumbing, stone, glass, metal, or signage
- invisible/sealed field joints
- specialty veneers, matched grain, curved work, unusual finishes, or mockups
- FSC/chain-of-custody or other documentation requirements
- conflicting furnished/installed responsibility across schedules and details

## Bid-risk output

Each run should produce a review queue including:

- missing information
- conflicting documents
- scope that appears in drawings but not responsibility schedules
- responsibility that cannot be resolved
- likely allowance items
- long-lead or vendor-dependent materials
- sustainability documentation burdens
- field-verification dependencies
- installation/coordination interfaces

## Cost model direction

The long-term model should be calibrated from JTI historical jobs. Generic construction unit prices can be used only as clearly labeled fallbacks.

Suggested cost buckets:

- sheet goods / lumber / veneer
- solid surface / stone
- metal / glass / specialty subcontractors
- hardware
- finish materials
- waste/yield
- CNC/programming/machining
- bench fabrication
- assembly
- finishing
- packaging/crating
- freight/delivery
- field installation
- travel/night work/site constraints
- engineering/shop drawings/project management
- sustainability/FSC administration
- contingency
- overhead
- margin

Actual-cost feedback from awarded/completed jobs should preserve the original estimate so model calibration is auditable over time.
