# Bid workflow overhaul — 0.4.15

Quote generation used to erase estimator confirmations on every reanalysis, including unchanged inputs. It now compares the current engine, document fingerprint, opportunity metadata, detected evidence, identity results and analysis errors with the last successful review. Confirmations survive only when those inputs and results remain unchanged. Changed inputs still rebuild unedited generated scope or preserve manual work with confirmations cleared.

## Behavior changes

- Background search, update and document-review jobs deliver results through a queue polled by the Tk UI thread. Worker failures and completion-handler failures restore the ready state and display their error.
- Starting or switching bids is disabled while a background job runs. The estimator opens as a modal window, and quote reanalysis runs behind a modal progress indicator.
- PDF and DOCX discovery accepts uppercase and mixed-case extensions. DOCX-only changes and deleted documents also make old reviews stale.
- Review rows retain their workspace-relative document paths. Same-name files in different subfolders no longer collapse into the same quote evidence. Ambiguous legacy basename references are left unresolved.
- The bid screen displays candidate scope and review-only evidence, with a detail view and a source-document button. Partial analysis is explicitly incomplete.
- Importing documents clears workflow confirmations and old customer quote files. Saving changed estimate data removes old quote files and the old AI review package; an identical save preserves them.
- Opportunity metadata changes invalidate the review. Project identity checking includes uppercase PDFs.
- Manifest, analysis JSON and estimate saves use same-directory temporary files and atomic replacement. A failed replacement retains the previous state.

## Validation

The regression suite exercises unchanged reanalysis, metadata changes, uppercase imports, nested evidence references, quote invalidation, DOCX-only changes, failed atomic saves, background errors and callback errors. The existing scope and project-identity tests remain in place.

Windows installation and visual GUI verification must be performed by the Windows build/smoke workflow and a desktop check. Python tests do not establish visual layout quality or correctness on real production bid packages. Document freshness still uses file size and nanosecond modification time; it is not a cryptographic content audit. OCR, automatic measured takeoff and vendor price feeds were not added in this change.
