# Phase 0 Build-Today Plan

## Status

This document now reflects the approved queue-centric MVP refinement that replaced the earlier session-only intake concept.

## Goal

Deliver the first usable Andent web intake vertical slice:
- FastAPI server starts
- users can upload one or more STL files from a browser page
- uploads populate a persistent `Active` queue with one classification row per file
- operators can review and edit `Model Type` and `Preset`
- eligible rows can move into a read-only `Processed` history via a simulated `Send to Print` handoff

## Locked Scope

- `API + browser-based queue intake UI`
- installation-level persisted queue state across refresh and restart
- `Active` and `Processed` tabs
- inline row editing for `Model Type` and `Preset`
- duplicate detection plus `Allow Duplicate`
- row removal with undo window
- simulated `Send to Print` that moves `Ready` rows into `Processed`

## Explicit Non-Goals

- build planning and packing
- support generation
- artifact export
- real printer dispatch
- real shared locking or named-user coordination
- separate exception-review workflow beyond row-level status/reason surfacing

## Recommended Build Order

### 1. Add the Phase 0 API contract
- Create a dedicated Andent router under `formflow_server/app/routers/`.
- Add upload request/response schemas in `formflow_server/app/schemas.py`.
- Return one row per uploaded STL with:
  - `file_name`
  - `case_id`
  - `model_type`
  - `preset`
  - `confidence`
  - `dimensions`
  - `review_required`
  - `review_reason`

### 2. Add lightweight persistent queue storage
- Add only the data model needed to persist active and processed rows.
- Avoid introducing the full future job/exceptions/artifacts model now.
- Keep persistence simple enough that the server can restart and still restore queue state for the same MVP slice.

### 3. Reuse classification logic directly
- Call `extract_case_id()` and `classify_artifact()` from `andent_classification.py`.
- Add the narrow mapping layer from current brownfield classifications to approved Phase 0 `Model Type` values.
- Surface low-confidence or ambiguous cases as table flags, not as separate review workflows.

### 4. Add the queue-centric browser page
- Reuse `formflow_server/static/` rather than introducing a new frontend stack.
- Add a page section for:
  - file chooser and drag/drop
  - automatic classification after selection
  - `Active` queue and `Processed` history tabs
  - inline editable `Model Type` and `Preset`
  - duplicate approval, row removal, and simulated submission actions
- Keep this page separate from the existing license dashboard path so the old admin flow is not disturbed.

### 5. Keep downstream behavior intentionally small
- Let the page edit queue rows after upload.
- Persist row state needed for the queue MVP.
- Do not connect edits or submission to downstream planning, support generation, export, or real dispatch yet.

## Concrete File Targets

- `formflow_server/app/main.py`
- `formflow_server/app/routers/__init__.py`
- new router such as `formflow_server/app/routers/andent.py`
- `formflow_server/app/models.py`
- `formflow_server/app/schemas.py`
- `formflow_server/static/index.html` or a dedicated Andent HTML entrypoint
- `formflow_server/static/app.js` or a dedicated Andent JS file
- `formflow_server/static/styles.css`
- `andent_classification.py`
- new tests under `tests/`

## Verification For Today

### Minimum proof
- server starts cleanly
- browser page loads with `Active` and `Processed` tabs
- uploading one STL returns one rendered row in `Active`
- uploading multiple STLs returns one row per file
- queue data survives browser refresh and server restart
- low-confidence or missing/ambiguous case IDs are visibly flagged
- `Model Type` and `Preset` can be edited in the page without running any downstream prep code
- duplicate rows can be promoted with `Allow Duplicate`
- `Ready` rows can move into `Processed` through the simulated handoff

### Test shape
- unit tests for classification mapping, review flagging, duplicate rules, and queue state transitions
- API tests for multipart upload, queue persistence, row edit actions, duplicate approval, delete, and simulated submission
- browser E2E for the queue-centric happy path plus the highest-risk UI edge cases

### Priority Browser E2E Gaps To Close
- status progression coverage: `Queued` -> `Uploading` -> `Analyzing` -> final status
- explicit `Check` and `Needs Review` browser cases, including missing/ambiguous case IDs
- status-legend filtering by visible chip labels
- `Model Type` auto-syncing `Preset` until a manual preset override exists
- manual correction promoting a `Check` or `Needs Review` row to `Ready`
- per-row `Allow Duplicate`, not just bulk duplicate approval
- manual deselection after case-aware auto-selection
- page-level `Select all` behavior and split-case exclusion messaging
- processed-table field checks for `Volume`, `Printer`, `Date`, and `Person`
- row-level undo countdown behavior using the intended spec duration
- simulated `Locked` state when focusing editable controls
- thumbnail click opening the 3D preview modal

## Risks

- Existing classification labels may not map cleanly into the approved five-value vocabulary.
- Reusing the current `static/index.html` entrypoint may collide with the license dashboard unless the routing is kept clean.
- Queue-centric UX behavior can drift from the approved PRD if the browser E2E only covers the happy path.
- If queue persistence grows into a full prep-job domain, this slice will drift into the next phase.

## Stop Condition

Phase 0 is complete when:
- the API works
- the queue-centric browser page works
- `Active` and `Processed` behavior matches the approved MVP refinement
- row fields and actions match the approved scope
- no downstream planning, support, export, or real dispatch behavior was accidentally pulled in
