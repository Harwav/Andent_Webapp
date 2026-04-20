# Test Spec: Andent Web

## Metadata
- Created: 2026-04-15T08:10:00Z
- Source plan: `Andent/02_planning/prd-andent-web-auto-prep.md`
- Source requirements: `Andent/01_requirements/prd-andent-web-auto-prep.md`

## Test Objectives
- Prove the web path can replace manual print-job preparation for standard cases.
- Prove exception routing is limited to the allowed decision boundaries.
- Prove exported artifacts and dispatch outcomes are durable and auditable.

## Approved Phase 0 Slice

> Phase 0 tests: COMPLETE as of 2026-04-18.
- Start the FastAPI server successfully.
- Upload one or more STL files.
- Restrict the returned `Model Type` values to:
  - `Ortho - Solid`
  - `Ortho - Hollow`
  - `Die`
  - `Tooth`
  - `Splint`
- Return a classification table row per file containing:
  - file name
  - detected case ID
  - detected model type
  - detected preset
  - confidence
  - dimensions
  - review-required state and reason
- Support model type and preset override without requiring downstream prep execution.

## MVP Refinement Coverage

### Queue Model
- Verify the UI exposes `Active` and `Processed` tabs.
- Verify the queue persists across browser refresh and server restart.
- Verify queue data behaves as one shared installation-level state rather than a browser-local session.
- Verify internal session/batch identifiers are not required in the visible MVP UI.

### Intake Flow
- Verify drag-drop accepts files and folders.
- Verify folder selection recursively includes only `.stl` files.
- Verify classification begins automatically after selection without a separate submit/classify step.
- Verify rows appear immediately with progressive status changes:
  - `Queued`
  - `Uploading`
  - `Analyzing`
  - final status
- Verify final user-facing statuses cover:
  - `Ready`
  - `Check`
  - `Needs Review`
  - `Duplicate`
  - `Locked`
- Verify the status legend filters rows by the visible status labels above.

### Classification And Editing
- Verify `Preset` uses the same dropdown options as `Model Type`.
- Verify changing `Model Type` auto-syncs `Preset` unless `Preset` has been explicitly overridden.
- Verify confidence is normalized into internal `high`, `medium`, and `low`.
- Verify user-facing final status mapping:
  - `high` -> `Ready`
  - `medium` -> `Check`
  - `low` -> `Needs Review`
- Verify manual correction of `Model Type`/`Preset` promotes a row to `Ready`.
- Verify manually corrected rows are visually indistinguishable from automatically ready rows.

### Duplicate Handling
- Verify duplicate detection uses STL content hash, not file name only.
- Verify duplicates are detected only against currently visible rows in `Active` or `Processed`.
- Verify deleted rows do not trigger later duplicate detection.
- Verify duplicates remain visible inline in `Active` with status `Duplicate`.
- Verify duplicate rows support the bulk `Allow Duplicate` action.
- Verify `Allow Duplicate` promotes an otherwise valid duplicate row to `Ready`.

### Selection, Pagination, And Submission
- Verify page size defaults to `50`.
- Verify `Active` defaults to grouping/sorting by `Case ID`.
- Verify `Processed` defaults to most recently submitted first.
- Verify selecting one row with `Case ID` auto-selects the rest of the visible matching case rows and preserves manual deselection.
- Verify rows without `Case ID` behave as standalone selections.
- Verify `Select all` applies only to rows visible on the current filtered page.
- Verify a case split across pages is excluded from bulk page selection and surfaced in the UI.
- Verify only `Ready` rows are eligible for `Send to Print`.
- Verify duplicate rows are selectable for `Allow Duplicate` before they are eligible for `Send to Print`.
- Verify mixed selections can expose both `Send to Print` and `Allow Duplicate` actions when applicable.

### Processed Tab
- Verify `Send to Print` immediately moves selected `Ready` rows from `Active` to `Processed`.
- Verify moved rows appear in `Processed` with status `Submitted`.
- Verify `Processed` is read-only in the MVP.
- Verify `Processed` columns include:
  - `Status`
  - `File`
  - `Case ID`
  - `Model Type`
  - `Preset`
  - `Volume`
  - `Printer`
  - `Date`
  - `Person`
- Verify `Date` shows the current known event time (`Submitted` now, later `Printed`) while the underlying record preserves audit history.

### Removal, Undo, And Locking
- Verify rows can be removed from `Active`.
- Verify removal starts a `10s` undo window and shows inline undo/countdown in the remove cell.
- Verify queued/uploading/analyzing rows are canceled immediately when removed.
- Verify rows are removed completely from the visible system when the undo window expires.
- Verify clicking into `Model Type` or `Preset` can place a row into a simulated `Locked` state.
- Verify locked rows disable editable controls in the UI.

### Table Layout And Preview
- Verify the `Active` table avoids horizontal scrolling at target viewport widths.
- Verify file names wrap up to 3 full lines without ellipsis.
- Verify `Dimensions` remains visible.
- Verify `Volume (mL)` is computed from raw STL mesh volume.
- Verify each row shows an automatic STL thumbnail.
- Verify clicking the thumbnail opens an interactive 3D modal preview.

## Launch Gates
- Straight-through processing rate: `>=95%`
- Human-review rate: `<=2%`
- Review triggers limited to:
  - low-confidence model type detection
  - ambiguous or missing case IDs

## Unit Coverage

### Classification And Decision Boundaries
- Verify model type detection reuses current classification behavior from `andent_classification.py:110`.
- Verify case ID extraction behavior from `andent_classification.py:78`.
- Verify low-confidence model type matches become review exceptions.
- Verify ambiguous or missing case IDs become review exceptions.
- Verify standard tooth and die jobs do not fail solely because of the retired MVP-era safety blocks.

### Planning And Packing
- Verify `BuildPlan.build_job_name()` remains deterministic (`andent_planning.py:71`).
- Verify same-case grouping remains intact through `plan_andent_builds()` (`andent_planning.py:200`).
- Verify build-family grouping and split logic behave deterministically (`andent_planning.py:245`, `andent_planning.py:307`).
- Verify cannot-fit cases route to review instead of partial processing (`andent_planning.py:286`).

### Headless Pipeline
- Verify the extracted headless pipeline produces status events without any Tkinter dependency that currently exists in `processing_controller.py:62` and `processing_controller.py:241`.
- Verify `.form` export calls map to `api_client.save_scene()` (`api_client.py:453`).
- Verify screenshot export calls map to `api_client.save_scene_screenshot()` (`api_client.py:477`).
- Verify support generation calls map to `api_client.auto_support_scene()` (`api_client.py:1142`).
- Verify printer dispatch calls map to `api_client.send_scene_to_local_printer()` (`api_client.py:324`).

### Server Domain
- Verify job, artifact, exception, and printer-group models persist and reload correctly.
- Verify job state transitions are valid and reject illegal transitions.
- Verify approval actions clear only valid exceptions and do not mutate successful jobs.

## Integration Coverage

### Upload To Job Creation
- Uploading a valid case package creates:
  - upload session
  - prep job
  - file records
  - initial status event
- Uploading a package with ambiguous case ID creates a review exception instead of dispatch.

### Phase 0 Classification Table
- Uploading STL files returns one row per file, even when files belong to the same case.
- Rows with unreadable STL dimensions are flagged clearly rather than silently dropped.
- Low-confidence model type matches are marked as review-required.
- Missing or ambiguous case IDs are marked as review-required.
- Model type and preset override update the row state without running packing, support generation, or dispatch.

### End-To-End Prep Pipeline
- A standard case flows through:
  - upload
  - classification
  - planning
  - support generation where required
  - `.form` export
  - screenshot export
  - printer-group dispatch
- The job record stores artifact paths and dispatch result.

### Exception Review
- A low-confidence model type match lands in the exception queue.
- An ambiguous or missing case ID lands in the exception queue.
- Approval clears the exception and resumes processing or requeues cleanly, depending on the selected design.
- Rejection marks the job as rejected without dispatch.

### Printer Group Routing
- Group policies resolve to the expected target printer(s).
- Invalid or missing printer-group configuration blocks dispatch and records an operational failure.
- Real-printer dispatch outcomes are stored as job events.

## End-To-End Coverage

### Browser Happy Path
- Drag-drop upload works in the browser.
- The job appears in the queue/status screen.
- Standard jobs auto-complete without manual preparation.
- Users can view/download the exported `.form` and screenshot.

### Browser Exception Path
- Outlier cases appear in the review queue with explicit reason text.
- Review actions are visible and auditable.
- No generic manual support-editing UI appears in phase 1.

## Observability Coverage
- Record straight-through processing numerator/denominator.
- Record human-review numerator/denominator.
- Record upload timestamp, processing start timestamp, artifact-complete timestamp, and dispatch timestamp.
- Record dispatch success/failure counts by printer group.
- Provide a report or dashboard extract suitable for launch sign-off.

## Test Data Strategy
- Reuse existing Andent fixtures and customer-facing validation material under `Andent/04_customer-facing/`.
- Include representative cases for:
  - standard ortho
  - standard tooth
  - standard splint
  - low-confidence model type cases
  - ambiguous/missing case ID cases
  - mixed-case uploads that remain in scope for the chosen web design

## Manual Validation Runs
- Run a controlled validation batch against representative uploads and confirm:
  - `>=95%` straight-through processing
  - `<=2%` human review
  - zero dispatches for rejected/review-blocked jobs
  - artifacts exist for each successful job

## Open Measurement Gaps
- Upload-to-queue latency target is still undefined and must be fixed before launch sign-off.
- Dispatch success-rate target is still undefined and must be fixed before launch sign-off.
- Mixed-model-type upload behavior should be explicitly locked during implementation planning if phase-1 support is desired.
