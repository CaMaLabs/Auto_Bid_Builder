# Quote reliability and release validation

Auto Bid Builder is an **estimator decision-support tool**, not a substitute for
a verified construction takeoff. A page-level term match, historical-price
similarity or an owner's whole-project budget is not sufficient evidence for
customer-facing pricing.

## Release-blocking cases

The Windows release must pass Python tests, frozen-app smoke test, and an
in-place installer upgrade test. The upgrade check installs the previous public
version in a temporary per-user directory, runs the new installer over it,
compares the installed executable SHA-256 to the newly built artifact and
smoke-tests the installed executable.

The following conditions block or invalidate quoting:

- **Wrong project**: Opportunity's explicit project number conflicts with the
  project number printed on bid package PDFs or indicated by consistent document
  filenames. Stop and move the files into the correct workspace.
- **Changed inputs**: PDF/DOCX names, sizes or modification times no longer
  match the last analysis. Mark review stale and reanalyze before quoting.
- **Analysis errors**: If any PDF/DOCX cannot be read, or the saved estimate
  cannot be refreshed, do not silently generate a new quote.
- **No scope**: Do not create a quote when there are no included scope lines.
- **Unverified generated scope**: Page-derived pricing remains DRAFT even when
  the generic review checkboxes are checked, until each generated item has
  been checked by an estimator against actual responsibility, quantity and
  construction details.
- **Invalid values**: Reject negative materials/labor/markup, negative labor
  rates, non-finite quantities or prices, nonpositive quantity, and tax outside
  0-100%.

## Scope suppression regression set

The test suite explicitly rejects false fabrication scope from:

- Electrical cabinets, NEMA enclosures, generator equipment and panelboards
- Communications cabinets, racks, plywood wiring backboards and conduit
- Access-control storage cabinets and shelves used for system equipment
- Door-hardware/key-control metal cabinets
- Appendix checklists asking about temporary change-room lockers
- Plumbing coordination mentions of existing millwork
- Architectural abbreviations and material/finish legends
- Typical blocking notes mentioning casework as an adjacent fixture

Positive controls retain fabrication candidates from architectural casework,
wood shelving and countertop specifications/drawings. References are evidence,
not automatically measured quantities.

## Document acquisition reliability

- Cal eProcure: visible "View Event Package" navigation and its guest relay
- SAM CSV: hydrate only the selected notice with the saved API key
- Public attachment links: extensionless download endpoints and generic
  octet-stream PDF signatures are recognized
- Repeated file imports: identical documents are not copied into numbered
  duplicates and counted again
- Controlled/login-required files: require normal authorized provider access

## Remaining constraints

- The current detector is **deliberately conservative**. It can still miss
  handwritten, scanned/image-only or unusually specified architectural scope.
- The quote suggestions do **not** constitute a complete physical quantity
  takeoff from every plan detail. Estimators must verify scope and quantities.
- Title blocks in unusual PDFs and project IDs that cannot be extracted remain
  "unknown", not verified. Missing identity evidence is not proof of a match.
- Live third-party portals can change markup, permissions and attachment
  endpoints. Regression tests use synthetic responses; field-site testing
  against authenticated portals is still required.

## Manual acceptance procedure

1. Verify the application version is visible in the main window.
2. Import a genuine architectural casework set: confirm correct sheet refs,
   preliminary items and clear DRAFT warnings until reviewed.
3. Import an unrelated electrical/security spec set: confirm no fabricated
   architectural millwork estimate is created.
4. Open a workspace for one project number and attach a PDF for another:
   verify a STOP error and no newly generated customer quote.
5. Add the same PDF twice: verify only one stored document/scope occurrence.
6. Alter a document after analysis: verify that its review is marked STALE.
7. Generate the quote: confirm analysis refresh, current source appendix and
   no stale previews; confirm any provisional assumptions remain labeled DRAFT.
8. Validate one direct SAM attachment and one Cal eProcure event-package route
   against actual public URLs. Logged-in resources require normal permission.
9. Run the built Windows installer over an installed prior version and compare
   executable SHA-256 against the release asset.

Do not put customer cost details, private source documents or bid history into
the public repository or its test fixtures.
