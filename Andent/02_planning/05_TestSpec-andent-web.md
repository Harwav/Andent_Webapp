# Test Spec: Andent Web Pre-Release QA Basis

## Metadata
- Created: 2026-04-15T08:10:00Z
- Last updated: 2026-04-28
- Status: Pre-release QA basis for MVP launch sign-off.
- Source plan: `docs/superpowers/plans/2026-04-27-launch-validation.md`
- Source requirements: `Andent/01_requirements/prd-andent-web.md`
- Implementation roadmap: `Andent/02_planning/04_Roadmap-implementation.md`

## Test Objectives
- Prove the web path can replace manual print-job preparation for standard cases.
- Prove exception routing is limited to the allowed decision boundaries.
- Prove exported artifacts and dispatch outcomes are durable and auditable.
- Prove the release candidate has executable, recorded evidence for every launch gate.

## Pre-Release Verdict Contract

This document is the release basis, not release evidence by itself. A release candidate is `RELEASE READY` only when every mandatory gate below has passed in the current candidate and the evidence bundle has been archived.

Release is `BLOCKED` when any of the following is true:
- The full pytest suite fails.
- The browser release gate fails.
- `scripts/validate_launch.py` fails or only produces classification-only dispatch evidence.
- A live PreFormServer handoff cannot be proven against `http://127.0.0.1:44388`.
- Human review is triggered for reasons outside the PRD boundaries.
- Required evidence is missing, stale, or from a different build/candidate.

The current known production blocker remains live PreFormServer dispatch proof unless a dated evidence bundle for the current candidate records it.

## Mandatory Launch Gates

| Gate | Target | Source of truth | Required evidence |
|------|--------|-----------------|-------------------|
| Full automated backend suite | 100% passing | `tests/` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/ -q` output |
| Browser smoke and release UI flows | 100% passing | `tests/release_gate/*.spec.ts` | Playwright output and report |
| Headed browser observation | Operator-visible run completed | `package.json` | `npm run test:release-gate:headed` output and operator note |
| Straight-through processing | `>=95%` | `app/services/metrics.py:123` | `/api/metrics/launch-check` plus validation script output |
| Human-review rate | `<=2%` | `app/services/metrics.py:123` | `/api/metrics/launch-check` plus validation script output |
| Upload p95 latency | `<=30s` | `app/config.py:103`, `app/services/metrics.py:123` | `/api/metrics/launch-check` plus validation script output |
| Dispatch success rate | `>=99%` and non-vacuous | `app/config.py:106`, `app/services/metrics.py:116` | At least one real live PreFormServer dispatch event, not an empty-dispatch calculation |
| Live PreFormServer handoff | Scene exists after send-to-print | `tests/release_gate/release_gate.spec.ts:4`, `tests/release_gate/helpers/fixtures.ts:24` | Playwright live handoff pass against `http://127.0.0.1:44388` |
| Review boundaries | Only low-confidence model type or ambiguous/missing case ID | `Andent/01_requirements/prd-andent-web.md` | Guard fixture results and manual validation notes |
| Artifact durability | `.form`/scene, screenshot/preview, print job manifest, and audit metadata are persisted | `tests/test_preform_handoff.py`, `tests/test_print_queue.py` | Database/job record proof plus operator artifact inspection |

## Pre-Release Runbook

Run these gates in order on the release candidate.

| Step | Command / action | Pass condition |
|------|------------------|----------------|
| 1. Environment health | Start the app with the intended release settings and verify `/health`, `/health/live`, and `/health/ready`. | All health endpoints return success. |
| 2. Backend suite | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/ -q` | All tests pass. |
| 3. TypeScript compile | `npx tsc --noEmit` | No TypeScript errors. |
| 4. Browser smoke and mocked UI release checks | `npx playwright test tests/release_gate/smoke.spec.ts tests/release_gate/ui-hooks.spec.ts tests/release_gate/bulk-actions.spec.ts --project=chromium` | All selected Playwright specs pass. |
| 5. Headed browser observation | `npm run test:release-gate:headed` | Chromium opens visibly; smoke/UI/bulk-action browser automation completes. |
| 6. Live PreFormServer availability | Confirm managed PreFormServer is installed, compatible, running, and reachable at `http://127.0.0.1:44388`. | Setup status is `ready`; version is recorded. |
| 7. Live browser handoff gate | `npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium` | Browser upload reaches send-to-print, print job is persisted, and scene lookup succeeds. |
| 8. Optional headed live handoff observation | `npm run test:release-gate:headed:live` | Chromium opens visibly and the live PreForm handoff flow completes. |
| 9. Launch metrics validation | `python scripts/validate_launch.py --base-url http://127.0.0.1:8090 --fixtures-dir "D:\Marcus\Desktop\BM\20260409_Andent_Matt\Test Data"` | Overall pass, with non-vacuous dispatch evidence. |
| 10. Manual operator validation | Run the checklist in `Manual Validation Runs`. | No blocker found; artifact and review-boundary notes recorded. |
| 11. Evidence archive | Save logs and outputs under `Andent/02_planning/98_VerificationArtifacts/pre_release_YYYYMMDD/`. | Evidence bundle contains all required files listed below. |

The npm script `test:release-gate` is not sufficient for release sign-off because it currently runs only `tests/release_gate/smoke.spec.ts`.

## Required Evidence Bundle

Create one dated folder per release candidate:

```text
Andent/02_planning/98_VerificationArtifacts/pre_release_YYYYMMDD/
```

Required contents:
- `pytest.log`: full backend suite output.
- `tsc.log`: TypeScript compile output.
- `playwright-smoke.log`: smoke/UI/bulk-action Playwright output.
- `playwright-headed.log`: headed smoke/UI/bulk-action Playwright output plus operator note.
- `playwright-live-preform.log`: live `release_gate.spec.ts` output.
- `validate-launch.log`: `scripts/validate_launch.py` output.
- `launch-check.json`: raw `GET /api/metrics/launch-check` response.
- `preform-status.json`: raw `GET /api/preform-setup/status` response.
- `dataset-inventory.md`: source dataset path, STL count, fixture-class mapping, and any excluded files.
- `print-job-evidence.json`: latest print job record including `scene_id`, `preset_names`, `compatibility_key`, `case_ids`, and `manifest_json`.
- `artifact-inventory.md`: operator-confirmed list of generated scenes/forms/screenshots or a note explaining why an artifact class is not produced in the current MVP.
- `verdict.md`: signed release verdict using the template at the end of this document.

Evidence from a run where dispatch success is vacuous because no PreFormServer was connected can support classification readiness, but cannot support production release.

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
- Verify `Printer` exposes `Form 4BL` and `Form 4B` choices and persists row-level changes.
- Verify bulk `Printer` updates persist for all selected editable rows.
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

### In Progress And History Sections
- Verify `Send to Print` moves selected `Ready` rows out of File Analysis into In Progress or History, depending on handoff state.
- Verify held rows appear in In Progress as `Holding for More Cases`.
- Verify submitted/printed rows are read-only after handoff.
- Verify In Progress rows expose individual removal but stay excluded from selection, bulk edits, and send-to-print actions.
- Verify History columns include:
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
- Verify removal starts a `5s` undo window and shows inline undo/countdown in the remove cell.
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

## Launch Gate Definitions

The release gates in `Mandatory Launch Gates` are interpreted as follows:

- Straight-through processing means a representative standard case reaches `Ready` and print handoff without a human model-type, preset, case-ID, or printer-group correction.
- Human-review rate counts rows/cases with `Needs Review`, `Check`, or human correction before release.
- Review is allowed only for:
  - low-confidence model type detection
  - ambiguous or missing case IDs
- Duplicate handling is a queue integrity workflow, not a classification failure, when the duplicate is correctly identified and not dispatched until explicitly allowed.
- Dispatch success is non-vacuous only when at least one selected `Ready` case reaches live PreFormServer handoff and produces persisted job/scene evidence.
- A launch metrics run with zero dispatch attempts must be labelled classification-only and cannot satisfy production release.

## Unit Coverage

### Classification And Decision Boundaries
- Verify model type detection reuses current classification behavior from `andent_classification.py:110`.
- Verify case ID extraction behavior from `andent_classification.py:78`.
- Verify low-confidence model type matches become review exceptions.
- Verify ambiguous or missing case IDs become review exceptions.
- Verify standard tooth and die jobs do not fail solely because of the retired MVP-era safety blocks.

### Planning And Packing
- Verify Form 4B/Form 4BL compatibility keys derive from preset metadata (`app/services/preset_catalog.py`).
- Verify same-case grouping remains intact through `plan_build_manifests()` (`app/services/build_planning.py`).
- Verify compatible mixed presets can share one build manifest.
- Verify incompatible presets never share a build manifest and incompatible same-case mixes route to manual review.
- Verify same-case mixed printer-group targets route to manual review.
- Verify largest/hardest-first seeding and smallest-case filler behavior remain deterministic.
- Verify estimated density is derived from effective XY footprint divided by the printer-group XY budget.
- Verify missing dimensions, missing file paths, missing row IDs, and oversized cases route to non-plannable manifest output instead of partial processing.
- Verify build-manifest preview uses the same planner as send-to-print (`app/services/planning_preview.py`).

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

### Form 4B/Form 4BL Build Manifest Handoff
- Compatible mixed presets share one PreFormServer scene when they resolve to the same printer group/material/layer-height family.
- Each uploaded case appears in at most one build manifest.
- PreFormServer import receives the per-file preset hint from the manifest import group.
- PreFormServer scene settings come from manifest printer group, material code, layer height, and print setting.
- Scene auto-layout and validation run before printer dispatch.
- Validation failure retries by removing whole cases only.
- A single seed case that fails validation is marked for manual review.
- Print job records persist `preset_names`, `compatibility_key`, printer group, material label/code, layer height, estimated density, validation result, validation errors, and manifest JSON for audit/debugging.

### Held Build Policy
- A final below-target build per compatibility group enters `Holding for More Cases` before cutoff.
- Held rows leave Active and remain in the In Progress workflow; unsent Active rows are never pulled in silently.
- Newly sent compatible rows replan with held rows while respecting planner budget.
- Above-target replanned builds dispatch and only a final below-target remainder stays held.
- Held builds persist across restart and do not auto-dispatch on startup after cutoff.
- Operator **Release now** releases a held build through the normal PreForm handoff path.
- Print Queue details show estimated density, target density, cutoff, hold reason, release reason, and validation warnings.

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
- Row and bulk printer-group choices are durable before dispatch.

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
- Use the external customer-style validation dataset at `D:\Marcus\Desktop\BM\20260409_Andent_Matt\Test Data` as the primary pre-release dataset.
- Record a fresh dataset inventory for every release candidate; on 2026-04-28 this folder contained 242 STL files, including 119 `UnsectionedModel`, 36 `Tooth`, 36 `Antag`, 2 `modeldie`, and 7 `modelbase` filename patterns.
- Use existing repo fixtures under `Andent/04_customer-facing/` and `tests/release_gate/fixtures/` as controlled guard fixtures when the external dataset does not cover a specific negative path.
- Include representative cases for:
  - standard ortho
  - standard tooth
  - standard splint
  - low-confidence model type cases
  - ambiguous/missing case ID cases
  - mixed-case uploads that remain in scope for the chosen web design

### Minimum Release Fixture Set

The release fixture set must include at least:

| Fixture class | Source | Required proof |
|---------------|--------|----------------|
| Standard ortho same-case multi-file package | External dataset, plus repo happy fixtures if needed | Auto-classifies, same-case selection works, live handoff creates one persisted print job. |
| Standard splint | External dataset if present; otherwise repo fixtures | Auto-classifies and uses the expected splint preset/handoff path. |
| Standard tooth/die | External dataset | Does not hit retired MVP safety blocks. |
| Ambiguous or missing case ID | External dataset if present; otherwise repo guard fixtures | Routes to review and does not dispatch. |
| Low-confidence or manually corrected case | Repo guard fixtures unless identified in external data | Review/correction behavior is explicit and auditable. |
| Duplicate content hash | Repo guard fixtures unless identified in external data | Duplicate is flagged, remains visible, and dispatch is blocked until `Allow Duplicate`. |
| Compatible mixed presets | External dataset | Compatible rows can share a build manifest when printer/material/layer-height match. |
| Incompatible mixed case | External dataset if present; otherwise repo guard fixtures | Routes to review or non-plannable output instead of partial silent processing. |
| Held below-target build | Repo/service fixtures, plus external small remainder if practical | Holds before cutoff, persists across restart, and releases only by valid trigger. |

If any fixture class is missing from the external dataset, fill the gap with repository fixtures and document that substitution in `dataset-inventory.md` and `verdict.md`.

## Automated Coverage Map

| Coverage area | Primary automated proof |
|---------------|-------------------------|
| Upload and classification | `tests/test_upload_classification.py`, `tests/test_parallel_classification.py`, `tests/test_live_validation.py` |
| Decision boundaries and metrics | `tests/test_metrics_service.py`, `tests/test_metrics_wiring.py` |
| Preset catalog and printer compatibility | `tests/test_preset_catalog.py`, `tests/test_release_gate_preset_normalization.py` |
| Build planning and batching | `tests/test_build_planning.py`, `tests/test_batching.py`, `tests/test_planning_preview.py` |
| PreFormServer client and handoff behavior | `tests/test_preform_client.py`, `tests/test_preform_handoff.py`, `tests/test_preform_setup.py` |
| Print queue persistence and polling | `tests/test_print_queue.py`, `tests/test_print_queue_schema.py`, `tests/test_print_queue_polling.py` |
| Frontend static contracts | `tests/test_frontend_static.py`, `tests/test_case_selection.py`, `tests/test_undo_removal.py`, `tests/test_polling.py` |
| Browser smoke and release UI flows | `tests/release_gate/smoke.spec.ts`, `tests/release_gate/ui-hooks.spec.ts`, `tests/release_gate/bulk-actions.spec.ts` |
| Live browser-to-PreForm handoff | `tests/release_gate/release_gate.spec.ts` |
| Release evidence helpers | `tests/test_release_gate_verify.py`, `tests/release_gate/helpers/python/release_gate_verify.py` |

## Manual Validation Runs
- Run a controlled validation batch against representative uploads and confirm the launch gates in `Mandatory Launch Gates`.
- Confirm PreFormServer setup UI reports `ready` before print handoff.
- Confirm selected standard cases move from File Analysis into In Progress or History after handoff.
- Confirm review-blocked rows do not dispatch.
- Confirm generated job evidence exists for each successful job:
  - persisted print job row
  - `scene_id`
  - manifest JSON
  - preset names
  - compatibility key
  - printer group/material/layer-height metadata
  - screenshot/preview or documented reason why unavailable
- Confirm visible UI states are understandable to an operator without developer console access.
- Confirm no sensitive local install path or token appears in the browser UI.

## Release Verdict Template

Create `verdict.md` in the dated evidence folder with this structure:

```markdown
# Andent Web Pre-Release Verdict - YYYY-MM-DD

## Candidate
- Commit:
- Branch:
- Operator:
- Machine:
- PreFormServer version:
- Primary dataset: `D:\Marcus\Desktop\BM\20260409_Andent_Matt\Test Data`
- App settings summary:

## Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| Backend pytest suite | PASS/FAIL | pytest.log |
| TypeScript compile | PASS/FAIL | tsc.log |
| Browser smoke/UI checks | PASS/FAIL | playwright-smoke.log |
| Headed browser observation | PASS/FAIL | playwright-headed.log |
| Live PreForm browser handoff | PASS/FAIL | playwright-live-preform.log |
| Straight-through rate >=95% | PASS/FAIL | validate-launch.log, launch-check.json |
| Human-review rate <=2% | PASS/FAIL | validate-launch.log, launch-check.json |
| Upload p95 latency <=30s | PASS/FAIL | validate-launch.log, launch-check.json |
| Dispatch success >=99%, non-vacuous | PASS/FAIL | validate-launch.log, print-job-evidence.json |
| Review boundaries | PASS/FAIL | fixture notes |
| Artifact durability | PASS/FAIL | artifact-inventory.md |

## Fixture Set
- Dataset inventory: dataset-inventory.md
- Standard ortho:
- Standard splint:
- Standard tooth/die:
- Review guard:
- Duplicate guard:
- Mixed compatibility:
- Held-build/release:

## Decision
- Verdict: RELEASE READY / RELEASE BLOCKED
- Blocking failures:
- Non-blocking risks:
- Follow-up owner:
```

## Remaining Release Risks

- Live PreFormServer dispatch proof is release-blocking until a current-candidate evidence bundle records it.
- `scripts/validate_launch.py` can report dispatch success as vacuously passing when no PreFormServer dispatch events exist; the verdict must reject that as production evidence.
- The package script `test:release-gate` runs only the smoke spec; release sign-off must run the broader Playwright commands in this document.
- A representative fixture set must be reviewed before each release. If the customer case mix changes, the fixture set must change with it.
- The planning docs include some historical phase language. The verdict should rely on this test spec, the current PRD, current code, and current evidence bundle.

## Resolved Measurement Gaps

| Former gap | Resolution |
|------------|------------|
| Upload-to-queue latency target undefined | Resolved as p95 `<=30s` via `app/config.py:103` and `app/services/metrics.py:123`. |
| Dispatch success-rate target undefined | Resolved as `>=99%` via `app/config.py:106` and `app/services/metrics.py:116`; production evidence must be non-vacuous. |
| Mixed-compatible Form 4B/Form 4BL behavior | Covered by build-planning and handoff tests; still requires live PreFormServer proof for the release candidate. |
