# RALPLAN PRD: Andent Web Auto Prep

## Metadata
- Created: 2026-04-15T08:10:00Z
- Source brief: `Andent/01_requirements/prd-andent-web-auto-prep.md`
- Source transcript: `Andent/00_context/interview-andent-web-auto-prep-20260415.md`
- Planning mode: `plan --consensus --direct` (manual consensus-style pass)
- Consensus status: approved
- Last updated: 2026-04-20
- Phase 1 status: In progress (~40%) — headless extraction complete, real handoff pending

## RALPLAN-DR Summary

### Principles
- Reuse proven Andent classification logic before inventing a new stack.
- Split web orchestration from Tkinter UI concerns so automation can run headlessly.
- Keep the happy path fully automatic; exceptions should be narrow, explicit, and auditable.
- **PreFormServer handles printer routing, dispatch, and print tracking** - not Andent Web.
- Preserve traceability with stored job state, review reasons, and classification metadata.

### Decision Drivers
- Brownfield leverage already exists in classification and build planning (`andent_classification.py:78`, `andent_classification.py:110`, `andent_planning.py:200`, `andent_planning.py:307`).
- The current prep pipeline is powerful but UI-coupled (`processing_controller.py:62`, `processing_controller.py:1211`, `processing_controller.py:1885`, `processing_controller.py:2005`).
- The repo already contains a FastAPI + SQLite service surface suitable for a web control plane (`formflow_server/app/main.py:69`, `formflow_server/app/main.py:161`, `formflow_server/app/database.py:21`, `formflow_server/app/database.py:46`).

### Viable Options
| Option | Summary | Pros | Cons |
| --- | --- | --- | --- |
| A. FastAPI web control plane + headless prep worker reusing current Python domain modules | Extend `formflow_server` for browser/API workflows and extract a worker-friendly orchestration layer from current prep code | Highest brownfield reuse, fits the new web requirement, keeps operator review/audit state server-side | Requires untangling GUI callbacks from `ProcessingController` |
| B. Thin browser shell over the current desktop UI | Keep desktop prep engine and remote-control it from a web front end | Lower initial refactor surface | Not a real web product, poor reliability, weak auditability, still operator-machine bound |
| C. Full web-native rewrite of classification, planning, and dispatch | Rebuild the full pipeline as a new service | Cleanest long-term architecture | Highest delivery risk, discards already-working Andent behavior |

### Decision
Choose **Option A**: extend the existing FastAPI service into the web control plane and extract a headless preparation worker from the current desktop pipeline.

### Invalidated Alternatives
- Option B rejected because it preserves desktop coupling and does not produce a credible web workflow with durable job state.
- Option C rejected because the product requirement changed to web delivery, not greenfield reinvention; the repo already has core prep logic worth keeping.

## ADR

### Decision
Build the new web product as a server-backed Andent workflow on top of `formflow_server`, while extracting reusable preparation orchestration from the existing desktop pipeline.

### Drivers
- Existing domain logic already covers classification, case grouping, packing, support generation, `.form` export, screenshots, and printer dispatch.
- Existing desktop orchestration is too tightly bound to Tkinter callbacks to serve directly as the web backend.
- A web product needs persistent upload/job/review state and role-based approval endpoints.

### Alternatives Considered
- Browser shell over the desktop app
- Full rewrite as a new web-native preparation engine

### Why Chosen
This path satisfies the new product shape without throwing away the brownfield assets that already solve the hard dental-preparation parts.

### Consequences
- `ProcessingController` must be split into reusable service logic and UI adapter behavior.
- The server will need new job, artifact, and exception data models.
- **Printer-group routing and dispatch are handled by PreFormServer** - not Andent Web.
- The browser experience becomes an API + queue system for intake and classification, not a full print management system.

### Follow-ups
- Define the exact classification/handoff boundary to PreFormServer.
- **Printer-group routing is PreFormServer's responsibility** - no need to define in Andent Web.
- Lock the launch metric queries and dashboards before rollout.

## Requirements Summary

The source brief requires a web application that accepts dropped files, uploads them, detects model type and case ID, assigns a preset from model type, and **hands off to PreFormServer** for downstream processing (orient/pack/support/dispatch). Human review is allowed only for low-confidence model type detection and ambiguous or missing case IDs, with a target of `<=2%` reviewed cases and `>=95%` straight-through classification accuracy.

> **Architecture clarification (2026-04-18):** PreFormServer handles orient/pack, support generation, job queue management, printer dispatch, and print status tracking. Andent Web's scope is intake, classification, and handoff.

Relevant brownfield evidence:
- Classification and case ID logic already exist in `andent_classification.py:78` and `andent_classification.py:110`.
- Build planning and case grouping already exist in `andent_planning.py:71`, `andent_planning.py:200`, and `andent_planning.py:307`.
- `.form` export, screenshot export, support generation, and dispatch already exist in `api_client.py:324`, `api_client.py:453`, `api_client.py:477`, and `api_client.py:1142`.
- The current orchestration is desktop/UI-bound in `processing_controller.py:62`, `processing_controller.py:1211`, `processing_controller.py:1885`, and `processing_controller.py:2005`.
- The current server already exposes FastAPI routers and SQLite persistence in `formflow_server/app/main.py:69`, `formflow_server/app/main.py:161`, and `formflow_server/app/database.py:21`.

## Acceptance Criteria
- A browser user can upload or drag-drop a case package and receive a durable job record with processing status.
- Standard cases proceed automatically through classification, case ID resolution, and preset assignment without operator touch.
- **Andent Web hands off prepared jobs to PreFormServer** (PreFormServer handles orient/pack/support/dispatch).
- Human review is triggered only for low-confidence model type detection or ambiguous/missing case IDs.
- Straight-through classification accuracy reaches `>=95%` on a representative launch-validation dataset.
- Human-review rate stays at or below `2%` on the same dataset.
- Phase 1 does not add manual support-tweaking tools or printer-fleet optimization features.

> **Note:** PreFormServer handles orient/pack, support generation, job queue management, printer dispatch, and print status tracking.

## Architecture Plan

### 1. Web Control Plane On Existing FastAPI Server
- Extend `formflow_server/app/main.py` with a new Andent router registration, following the current router pattern at `formflow_server/app/main.py:161`.
- Add job APIs under a new router such as `formflow_server/app/routers/andent_jobs.py`.
- Reuse the existing FastAPI + SQLite foundation from `formflow_server/app/database.py:21` and `formflow_server/app/database.py:46`.
- Add static/admin pages or a dedicated front-end shell under `formflow_server/static/` for upload, exception review, and job-status views.

### 2. Headless Prep Worker Extraction
- Extract reusable orchestration from `ProcessingController` into a non-Tkinter module, because the current controller takes `gui_callback_handler` in `processing_controller.py:57-63` and emits UI state throughout the run.
- Preserve domain steps already implemented:
  - build planning via `_build_execution_plans` and Andent planning flow (`processing_controller.py:1211`, `andent_planning.py:200`)
  - support generation (`processing_controller.py:1057`, `api_client.py:1142`)
  - screenshot export (`processing_controller.py:978`, `api_client.py:477`)
  - `.form` export (`processing_controller.py:1934`, `api_client.py:453`)
  - dispatch (`processing_controller.py:2005`, `api_client.py:324`)
- Introduce a service-facing callback/event interface so web/API status updates replace Tkinter dialogs and progress widgets.

### 3. Upload, Job, And Exception Domain
- Add server-side models for uploaded file groups, resolved cases, execution jobs, artifacts, review exceptions, and printer groups in `formflow_server/app/models.py`.
- Add matching request/response schemas in `formflow_server/app/schemas.py`.
- Persist enough state to support:
  - upload receipt
  - processing status transitions
  - exception reason
  - review approval/rejection
  - artifact paths
  - dispatch outcome

### 4. Shared Domain Reuse
- Reuse `andent_classification.py` as the source of truth for model type and case ID detection.
- Reuse `andent_planning.py` job naming and case-based packing behavior, especially `BuildPlan.build_job_name()` in `andent_planning.py:71`.
- Reuse `batch_optimizer.py:96`, `batch_optimizer.py:201`, and `andent_planning.py:307` for build-fit logic instead of replacing packing heuristics in phase 1.

### 5. Handoff to PreFormServer

- **PreFormServer handles:** orient/pack, support generation, job queue management, printer dispatch, print status tracking.
- Andent Web's responsibility ends at classification + preset assignment + sending prepared job metadata to PreFormServer API.
- No printer-group routing or dispatch logic in Andent Web backend.
- The `send_rows_to_print` action in Phase 0 simulates handoff; real PreFormServer integration will replace it in Phase 1.

### 6. Exception-Only Human Review
- Preserve the source brief's narrow decision boundary: only low-confidence model type matches and ambiguous/missing case IDs should stop automation.
- Convert current manual-review reporting from `processing_controller.py:934` into server-visible exception records and approval actions instead of local file/report popups.
- Do not carry forward the older tooth auto-prep and dispatch safety blocks as product policy for standard cases.

## Implementation Steps

### Phase 1. Artifact And Domain Setup
- Add the new requirement and planning docs to `Andent/01_requirements` and `Andent/02_planning`.
- Add new SQLAlchemy models and migrations in `formflow_server/app/models.py` and `formflow_server/app/database.py` for:
  - upload sessions
  - prep jobs
  - job artifacts
  - review exceptions
  - printer groups

### Phase 2. Headless Pipeline Extraction

> **Status (2026-04-20):** Headless extraction complete (commits fdabf3c, 6fbc170, 41c58a9). Real PreFormServer handoff still pending.

- Create a headless orchestration module, for example `processing_pipeline.py` or `andent_service_pipeline.py`, that wraps current prep operations without Tkinter.
- Move status/error/report logic behind an adapter interface so the same core run can be used from the web service and the desktop UI.
- Keep current `ProcessingController` as a UI adapter over the extracted service during migration.

### Phase 3. Server APIs
- Add upload/create-job/status/review/approve endpoints in new `formflow_server/app/routers/andent_jobs.py`.
- Register the new router in `formflow_server/app/main.py`.
- Add schemas for upload requests, job summaries, review decisions, and artifact metadata in `formflow_server/app/schemas.py`.

### Phase 4. Browser Workflow
- Add a browser upload and review surface under `formflow_server/static/` for:
  - drag-drop uploads
  - job queue/status
  - exception review and approval
  - artifact preview/download
- Keep phase 1 UI tightly scoped to operational flow; do not add manual support editing tools.

### Phase 5. Printer Group Dispatch
- Add persisted printer-group configuration and mapping.
- Resolve printer-group policies server-side and pass the final target to `send_scene_to_local_printer()`.
- Store dispatch attempts and outcomes as job events for auditability.

### Phase 6. Metrics And Rollout Guardrails
- Emit operational counters for:
  - straight-through processing rate
  - human-review rate
  - upload-to-queued latency
  - dispatch success rate
- Gate rollout on representative sample-data validation from `Andent/04_customer-facing/` and any additional production-like uploads.

## Approved Execution Phases

### Phase 0. Classification Intake Vertical Slice
Goal:
- start the server, upload STL files, and return a usable classification table before deeper automation work begins

Work:
- add a minimal upload endpoint and a minimal browser upload/classification page on the existing FastAPI server
- accept one or more STL files and persist them as a lightweight upload session
- run existing classification logic from `andent_classification.py`
- map classification output into the approved `Model Type` vocabulary:
  - `Ortho - Solid`
  - `Ortho - Hollow`
  - `Die`
  - `Tooth`
  - `Splint`
- return a classification table per file with:
  - file name
  - detected case ID
  - detected model type
  - detected preset
  - model type confidence
  - model dimensions
  - review-required flag and reason
- allow operator override of the detected model type and preset before any downstream preparation exists
- keep Phase 0 override edits session-scoped; durable override save moves to the next phase
- define the minimal API/schema contract for this table response

Primary files:
- `formflow_server/app/main.py`
- new router such as `formflow_server/app/routers/andent_jobs.py`
- `formflow_server/app/models.py`
- `formflow_server/app/schemas.py`
- `formflow_server/static/`
- `andent_classification.py`

Exit criteria:
- server starts and accepts STL uploads
- upload returns a classification table for each file
- browser upload/classification page can submit STL files and render the returned rows
- model type and preset override are supported in API/UI row state without triggering downstream prep work
- dimensions and confidence are visible for every successfully parsed STL
- ambiguous/missing case IDs and low-confidence matches are surfaced explicitly in the table

### Phase 1. Headless Core Extraction
Goal:
- separate reusable preparation orchestration from Tkinter dependencies so the pipeline can run as a backend service

Work:
- extract a service-oriented pipeline from `ProcessingController`
- replace GUI callbacks with an event/callback adapter interface
- keep the current desktop path working through a UI adapter during migration
- preserve existing Andent classification, planning, support, screenshot, export, and dispatch behavior

Primary files:
- `processing_controller.py`
- new module such as `andent_service_pipeline.py`
- `andent_classification.py`
- `andent_planning.py`
- `api_client.py`

Exit criteria:
- the prep pipeline can run without Tkinter objects
- desktop flow still works through an adapter
- regression tests cover extracted domain behavior

### Phase 2. Server Domain And Job Persistence
Goal:
- create durable server-side storage for uploads, jobs, exceptions, artifacts, and printer groups

Work:
- add SQLAlchemy models for upload sessions, prep jobs, job artifacts, exception items, and printer groups
- add schemas and validation for API payloads
- add migration/init logic for the new tables
- store status transitions and event history for auditability

Primary files:
- `formflow_server/app/models.py`
- `formflow_server/app/schemas.py`
- `formflow_server/app/database.py`

Exit criteria:
- jobs survive server restart
- artifact and exception records are queryable
- state-transition rules are test-covered

### Phase 3. API Surface And Worker Wiring
Goal:
- expose the web-prep workflow through FastAPI and connect it to the headless prep pipeline

Work:
- add upload/create-job/status/list/review/approve endpoints
- register the new router in the FastAPI app
- connect API job creation to the headless worker/service layer
- return structured progress, artifact, and exception data

Primary files:
- `formflow_server/app/main.py`
- new router such as `formflow_server/app/routers/andent_jobs.py`
- `formflow_server/app/schemas.py`
- headless pipeline module from Phase 1

Exit criteria:
- API can create and track jobs end-to-end
- exception cases are visible through API responses
- successful jobs produce persisted artifact metadata

### Phase 4. Browser Intake And Review UI
Goal:
- deliver the operator-facing web flow for drag-drop intake, job visibility, and exception review

Work:
- build upload UI with drag-drop
- build queue/status screens
- build exception-review UI with explicit approve/reject actions
- build artifact preview/download surface
- exclude manual support editing and fleet optimization controls

Primary files:
- `formflow_server/static/*`
- any new front-end JS/CSS/HTML assets
- new API routes consumed by the UI

Exit criteria:
- browser happy path works for standard cases
- exception path is usable and auditable
- no out-of-scope manual-editing UI appears

### Phase 5. Printer Group Routing And Dispatch Policy
Goal:
- make dispatch deterministic and server-owned rather than desktop-selection owned

Work:
- model printer groups and group membership
- implement group resolution before dispatch
- record dispatch attempts, outcomes, and retries if supported
- preserve explicit controls for real-printer dispatch policy

Primary files:
- `formflow_server/app/models.py`
- `formflow_server/app/routers/andent_jobs.py`
- headless pipeline module
- `api_client.py`
- `local_printer_controller.py`

Exit criteria:
- standard jobs dispatch through server-side printer-group rules
- blocked/review jobs never dispatch
- dispatch audit trail is queryable

### Phase 6. Validation, Metrics, And Launch Readiness
Goal:
- prove the system meets the phase-1 operational bar on representative data before rollout

Work:
- run unit, integration, and end-to-end suites
- validate on representative Andent sample data
- compute straight-through and review-rate metrics
- verify artifact generation and dispatch auditability
- document residual risks and rollout gate decision

Primary files:
- `Andent/02_planning/test-spec-andent-web-auto-prep.md`
- test modules under `tests/`
- server-side metric/reporting code

Exit criteria:
- `>=95%` straight-through processing
- `<=2%` human review
- no unexpected dispatches for blocked jobs
- approval package for launch sign-off is complete

## MVP Refinement: Queue-Centric Intake And Submission UI

This refinement replaces the earlier session-first intake/table concept with a persistent shared queue model that is easier to operate in production.

### Product Direction
- The UI centers on two tabs:
  - `Active`: shared working queue for uploaded STL rows
  - `Processed`: read-only history for rows that have been sent onward and are currently `Submitted` (later `Printed`)
- Queue data is installation-level and persists across browser refreshes, app restarts, and multiple operators on the local network.
- Internal batch/session IDs may still exist for storage, audit, or debugging, but they are not shown as a user-facing concept in the MVP.

### Active Tab UX
- Upload area behavior:
  - drag-drop accepts files or folders
  - clicking the dropzone opens the file picker
  - the visible action button remains `Select Folder`; file picking stays on the dropzone click-path
  - folder selection recursively includes only `.stl` files
  - classification starts automatically after selection; no separate `Classify Upload` action remains
- Table behavior:
  - rows appear immediately after selection
  - each row uses one unified status chip
  - in-progress states: `Queued`, `Uploading`, `Analyzing`
  - final review states: `Ready`, `Check`, `Needs Review`, `Duplicate`, `Locked`
  - legend items are clickable and filter rows by the visible status labels above
- Table layout avoids horizontal scrolling:
  - file names wrap up to 3 full lines without ellipsis
  - dimensions remain visible
  - add `Volume (mL)` from raw STL mesh volume
  - include automatic STL thumbnail per row
  - clicking the thumbnail opens an interactive 3D preview in a modal overlay

### Classification And Edit Rules
- `Preset` is a dropdown using the same options as `Model Type`.
- Changing `Model Type` auto-syncs `Preset` unless the user later overrides `Preset`.
- Confidence is internally modeled as `high`, `medium`, and `low`.
- User-facing status mapping is:
  - `high` -> `Ready`
  - `medium` -> `Check`
  - `low` -> `Needs Review`
- `Medium` covers weaker-but-usable evidence such as geometry fallback or partial filename cues.
- `Low` is reserved for unclassified, conflicting, or manual-attention cases.
- When the operator manually corrects `Model Type` and/or `Preset`, the row becomes `Ready` automatically and looks identical to any other `Ready` row.

### Duplicate Rules
- Duplicate detection uses actual STL content hash.
- A row is marked `Duplicate` only when its content hash matches a currently visible row in `Active` or `Processed`.
- Deleted rows do not participate in later duplicate checks.
- Duplicate rows remain visible in `Active` like any normal row.
- Duplicate rows can be selected for the bulk `Allow Duplicate` action.
- `Allow Duplicate` immediately promotes the row to `Ready` when its classification is otherwise valid.

### Selection And Submission Rules
- `Active` supports multi-select with:
  - per-row selection
  - case-aware auto-selection when a row with `Case ID` is selected
  - page-level `Select all`
- Selection rules:
  - selecting one row auto-selects all rows with the same `Case ID`, even across upload times
  - users can manually deselect specific rows afterward
  - rows without `Case ID` behave as standalone selections only
  - `Select all` applies only to currently visible rows on the current page after filters
  - if a case is split across pages, that partial case must be excluded from bulk page selection and surfaced in the UI
- Pagination:
  - default page size is `50`
  - `Active` defaults to grouping/sorting by `Case ID` to reduce page splitting
  - `Processed` defaults to most recently submitted first
- Eligibility:
  - only `Ready` rows are eligible for `Send to Print`
  - duplicate rows are selectable for `Allow Duplicate`, not for `Send to Print`, until promoted to `Ready`
  - non-eligible rows show disabled selection for print submission
- The bulk action bar can show both `Send to Print` and `Allow Duplicate` when the current selection mix supports both actions.

### Active -> Processed Flow
- `Send to Print` is the simulated MVP handoff action.
- On submission:
  - selected `Ready` rows immediately leave `Active`
  - they appear in `Processed`
  - their status becomes `Submitted`
- `Processed` is read-only in the MVP.
- `Printed` will be updated later from real downstream job-state integration, not manual UI actions in this phase.

### Processed Tab MVP Fields
- `Processed` columns:
  - `Status`
  - `File`
  - `Case ID`
  - `Model Type`
  - `Preset`
  - `Volume`
  - `Printer`
  - `Date`
  - `Person`
- `Date` is a single current-known-event date column:
  - `Submitted` date for now
  - later `Printed` date when available
- The persistent record still keeps an internal audit trail of status/event history for later reference even if the table shows only one current date.
- `Printer`, `Date`, and `Person` may use placeholder values such as `-` until later integrations exist.

### Row Removal And Undo
- Each row has a remove action in `Active`.
- Removing a row also removes it from the persisted queue/state after a `10s` undo window.
- During that window, the remove icon is replaced inline with `Undo` and countdown feedback in the same cell.
- If a row is still `Queued`, `Uploading`, or `Analyzing`, removal cancels it immediately and starts the same undo window.
- After the timer expires, the row is removed completely from the visible system.

### Locking For MVP
- Include a simple UI-level simulated `Locked` state for rows when a user clicks into `Model Type` or `Preset`.
- Locked rows disable editable controls in the UI treatment, but no real shared backend lock is required in this MVP.
- Future named-user locking and real cross-browser coordination remain deferred to later phases.

## Phase Ordering
- `Phase 0` is the approved first executable milestone.
- `Phases 1-3` are approved as the next implementation tranche:
  - `Phase 1`: Session Persistence And Override Save
  - `Phase 2`: Headless Core Extraction
  - `Phase 3`: Planning Preview
- `Phases 4-6` remain intentionally sequenced after the `Phase 1-3` tranche review checkpoint.

## Approved Next Tranche

The next approved delivery tranche is:
- `Phase 1`: persist upload sessions, per-file classifications, and operator overrides
- `Phase 2`: extract a headless preparation core from the Tkinter-bound pipeline
- `Phase 3`: expose a planning preview that shows what the server will do before preparation or dispatch is enabled

Tranche rationale:
- `Phase 1` makes Phase 0 durable and operationally useful
- `Phase 2` removes the main backend architecture blocker
- `Phase 3` lets planning logic be validated before preparation and dispatch complexity are introduced

## Risks And Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| GUI coupling leaks into the web path | Slow migration and fragile backend behavior | Extract a headless service layer first; keep Tkinter as an adapter, not the orchestrator |
| Server-side job persistence is underspecified | Lost audit trail and poor recoverability | Add explicit job/artifact/exception tables and state transitions before web UI work |
| Auto-dispatch goes to the wrong device group | Operational printing failures | Make printer-group routing explicit, persisted, and test-covered before enabling production auto-dispatch |
| Existing heuristics underperform on browser-uploaded datasets | Straight-through rate misses `>=95%` target | Validate on representative datasets and keep exception routing narrow but honest |
| Approval scope expands into a generic editing UI | Phase-1 scope creep | Keep review UI decision-only; reject manual support editing and fleet optimization from phase 1 |

## Verification Steps
- Unit-test classification, case grouping, job naming, exception routing, and printer-group resolution.
- Integration-test upload-to-job persistence, headless prep execution, `.form`/screenshot artifact generation, and dispatch recording.
- End-to-end test browser upload, exception review, approval, and automatic dispatch flows against a controlled printer-group environment.
- Validate launch metrics on representative Andent sample data with explicit straight-through and review-rate reporting.

## Available Agent Types Roster
- `planner`
- `architect`
- `critic`
- `executor`
- `debugger`
- `test-engineer`
- `verifier`
- `designer`
- `writer`

## Follow-up Staffing Guidance

### If Using `$ralph`
- Use one primary execution lane with `high` reasoning to drive:
  - headless pipeline extraction
  - FastAPI job/domain additions
  - browser upload/review flow
  - verification evidence collection

### If Using `$team`
- Lane 1: backend domain and DB models (`high`)
- Lane 2: headless processing extraction and dispatch pipeline (`high`)
- Lane 3: web upload/review UI and API wiring (`medium`)
- Lane 4: test/verification harness and launch metrics (`medium`)

## Launch Hints

```text
$ralph .omx/plans/prd-andent-web-auto-prep.md
```

```text
$team .omx/plans/prd-andent-web-auto-prep.md
```

## Team Verification Path
- Team proves:
  - upload-to-job persistence works
  - standard jobs auto-run end-to-end
  - exception-only review path works
  - dispatch outcomes are recorded
- Ralph or a final verifier proves:
  - `>=95%` straight-through processing on the chosen validation dataset
  - `<=2%` review rate
  - no manual support-editing or fleet-optimization scope creep was introduced

## Changelog
- Chose a brownfield web-control-plane architecture instead of a desktop wrapper or full rewrite.
- Anchored the plan to concrete existing files for classification, planning, export, screenshot, dispatch, server, and settings reuse.
