# Andent Web PRD

> **Status:** Phase 1 repository implementation complete. Pre-release validation failed (2026-04-28) — 9/9 gates blocked: TypeScript compile errors, browser smoke test failures, live PreForm handoff timeout, launch validation timeout. See `Andent/02_planning/98_VerificationArtifacts/pre_release_20260428/verdict.md` for full evidence.

## Metadata

- Profile: `standard`
- Rounds: `6`
- Final ambiguity: `14.7%`
- Threshold: `20%`
- Context type: `brownfield`
- Context snapshot: `Andent/00_context/context-andent-web-auto-prep-20260415.md`
- Transcript: `Andent/00_context/interview-andent-web-auto-prep-20260415.md`

## Clarity breakdown

| Dimension | Score |
| --- | --- |
| Intent | 0.87 |
| Outcome | 0.80 |
| Scope | 0.88 |
| Constraints | 0.84 |
| Success | 0.90 |
| Context | 0.84 |

## Intent

Eliminate manual preparation of print jobs.

## Desired Outcome

A web-based application that accepts dropped case files, uploads them, classifies model type and preset, confirms or derives case identity automatically, prepares classification metadata, and **hands off to PreFormServer** for downstream processing (orient, pack, supports, dispatch, tracking).

## In Scope

- Browser-based file drop intake for case files.
- Upload pipeline for incoming files.
- Automatic model type detection.
- Automatic preset assignment based on model type, with operator override support.
- Automatic case ID confirmation / derivation on the happy path.
- Human review flow only for defined outliers.
- Compatibility-aware Form 4B/Form 4BL build planning that keeps each case intact and allows only same-printer-group/material/layer-height mixed presets.
- Operator-selectable printer group per row and in bulk, with default `Form 4BL` behavior.
- Density-based holding for the final below-target build per compatibility group, with cutoff release and operator **Release now**.
- **Handoff to PreFormServer** for downstream processing.

> **PreFormServer handles:** orient/pack, support generation, job queue management, printer dispatch, print status tracking.

Phase-1 `Model Type` values:
- `Ortho - Solid`
- `Ortho - Hollow`
- `Die`
- `Tooth`
- `Splint`

## Out-of-Scope / Non-goals

- Manual support tweaking tools in phase 1.
- Printer-fleet optimization in phase 1.
- Job queue management (handled by PreFormServer).
- Printer dispatch (handled by PreFormServer).
- Print status tracking (handled by PreFormServer).
- Orient & pack (handled by PreFormServer).
- Support generation (handled by PreFormServer).

> **Architecture clarification (2026-04-18):** PreFormServer API handles all print-related operations. Andent Web's scope is limited to intake, classification, review, and handoff to PreFormServer.

## Decision Boundaries

The system may proceed without human confirmation when:

- model type detection is confident
- case ID is confidently determined

The system must stop and route to human review when:

- model type detection is low confidence
- case ID is ambiguous or missing

The system should not require human review for standard die/tooth support generation or standard printer-group dispatch merely because those steps were previously blocked in the MVP.

## Constraints

- Human review should be limited to outliers and should not exceed `2%` of cases.
- Prior MVP-era safeguards blocking tooth-model auto-prep and printer auto-dispatch should be removed for standard cases in this PRD.
- This is a phase-1 PRD for a web product, not a desktop-only extension.

## Testable Acceptance Criteria

- The system achieves `>=95%` straight-through processing at launch.
- Standard cases complete the following **within Andent Web** without operator touch:
  - model type detection
  - preset assignment
  - case ID confirmation
- Human review is reserved only for:
  - low-confidence model type matches
  - ambiguous or missing case IDs
- Human-reviewed outliers remain at or below `2%` of total cases.
- Standard die/tooth cases are not blocked by the previous MVP-era tooth support safety gate.
- **Andent Web sends prepared jobs to PreFormServer** (PreFormServer handles orient/pack/support/dispatch).

> **Note:** PreFormServer handles orient/pack, support generation, job queue management, printer dispatch, and print status tracking. Andent Web's acceptance criteria focus on intake-to-handoff accuracy.

### Acceptance Checklist (2026-04-28)

> ⚠️ Pre-release validation failed. See `Andent/02_planning/98_VerificationArtifacts/pre_release_20260428/verdict.md` for evidence.

| Acceptance Criterion | Status | Evidence |
| --- | --- | --- |
| The system achieves `>=95%` straight-through processing at launch. | ❌ Not Proven | Launch validation timed out during 242-file upload. Metric infrastructure exists but live proof is missing. |
| Standard cases complete without operator touch: | | |
| `model type detection` | ✅ Done | Repository + pytest green |
| `preset assignment` | ✅ Done | Repository + pytest green |
| `case ID confirmation` | ✅ Done | Happy-path derivation exists |
| Human review reserved only for: | | |
| `low-confidence model type matches` | ✅ Done | Implemented in `app/services/classification.py` |
| `ambiguous or missing case IDs` | ✅ Done | Implemented in `app/services/classification.py` |
| Human-reviewed outliers remain `<=2%` of total cases. | ❌ Not Proven | Metrics calculation exists; live proof missing |
| Standard die/tooth cases not blocked by MVP-era safety gate. | ✅ Done | Repository + pytest green |
| Compatible mixed presets share one Form 4B/Form 4BL build. | ✅ Done | Repository + pytest green |
| Operators can persist printer group target. | ✅ Done | Row-level + bulk update endpoints green |
| Below-target builds hold until target, cutoff, or release. | ✅ Done | Hold/release logic implemented |
| **PreFormServer handoff** | ✅ Repo / ❌ Live | Repository code exists; browser handoff gate failed (timeout) |
| Complete approve/reject review workflow | ⚠️ Partial | Row-level override exists; full review queue UI not yet built |

## Approved Phase 0 Scope

Phase 0 delivered classification intake (FastAPI server, STL upload, classification table, editable Model Type/Preset). **Complete as of 2026-04-18.** See `Andent/99_archive/phase-0-build-today.md` for full detail.

## Current Repository Snapshot (2026-04-27)

Implemented in the repository:

- intake/classification queue with editable model type and preset
- case ID derivation and review-required flags for low-confidence or missing-ID rows
- preset catalog and compatibility-aware Form 4B/Form 4BL build manifests
- durable operator printer-group edits in the Work Queue and bulk action bar
- density-based Holding for More Cases state, cutoff metadata, and operator Release now path
- PreFormServer handoff route and print job persistence
- Print Queue UI, Formlabs job polling, and screenshot retrieval/caching
- read-only plan preview endpoints backed by the same build-manifest planner used for handoff

Not yet proven complete against launch acceptance:

- straight-through rate `>=95%`
- human review rate `<=2%`
- a complete approve/reject review workflow beyond row-level override

Current verification state:

- automated repository verification is now green (`250 passed` with plugin autoload disabled in this environment)
- TypeScript checking is green (`npx tsc --noEmit`)
- affected Playwright bulk-actions release gate is green (`2 passed` on `ANDENT_PLAYWRIGHT_PORT=53123`)
- remaining confidence gaps are operational rather than code-path blockers: live workflow metrics and real service/hardware validation

## Assumptions Exposed And Resolutions

- Assumption: current brownfield safeguards around tooth auto-prep and dispatch might still be required.
  - Resolution: explicitly rejected for standard cases.
- Assumption: multiple operational exceptions might need human review.
  - Resolution: outlier handling is intentionally narrow and limited to low-confidence classification and ambiguous/missing case IDs.

## Pressure-pass Findings

- Pressure pass revisited the existing repository safety model rather than accepting it as a product requirement.
- Clarified requirement: remove current Andent MVP restrictions on tooth auto-prep and printer auto-dispatch for standard cases.

## Brownfield Evidence Vs Inference

### Evidence from repository

- `andent_classification.py` contains model-type classification and case ID extraction logic.
- `api_client.py` contains auto-support and printer dispatch primitives.
- `app_gui.py` contains queue and printer-selection concepts.
- `Andent/04_customer-facing/mvp-local-test-guide.md` documents that the current MVP intentionally avoids printer dispatch and tooth-model automation.

### Inference

- A web product can likely reuse or wrap parts of the current classification, planning, and dispatch logic, but exact architecture remains for planning.

## Technical Context Findings

- Relevant likely touchpoints:
  - `andent_classification.py`
  - `andent_planning.py`
  - `processing_controller.py`
  - `api_client.py`
  - `local_printer_controller.py`
  - `app_gui.py`
- Brownfield tension explicitly resolved:
  - current safety limits are implementation-era constraints, not phase-1 PRD constraints

## Condensed Transcript

1. Business outcome: eliminate manual preparation of print jobs.
2. Required automation (Andent Web scope): classification, case ID confirmation, preset assignment, and handoff to PreFormServer.
3. Allowed human-review triggers: low-confidence model type detection and ambiguous/missing case IDs.
4. Existing tooth auto-prep and dispatch safeguards: remove them for standard cases.
5. Phase-1 non-goals: manual support tweaking tools and printer-fleet optimization.
6. **PreFormServer handles:** orient/pack, support generation, job queue management, printer dispatch, print status tracking.
7. Launch success metric: `>=95%` straight-through classification accuracy.

## Recommended Next Step

Current repo state no longer needs a fresh planning handoff first. The next accurate branch is launch acceptance proof:

- collect live workflow metrics before claiming the `>=95%` straight-through and `<=2%` review targets
- run a live PreFormServer/Formlabs validation pass against real services
- document the operational evidence alongside this PRD once collected

## Residual Risks

- The repo now contains much of the intended Phase 1 surface, but launch-readiness is still limited by verification rather than feature absence.
- The spec sets a clear straight-through target, but the current implementation still lacks repository-backed proof for:
  - upload-to-queue latency target under representative load
  - printer dispatch success-rate target
  - live-service behavior for mixed-compatible Form 4B/Form 4BL builds and held-build release
- Those should be closed through stabilization and validation, not by reopening product intent.

### Performance Targets (2026-04-28)

The following targets were identified as missing from the original PRD and should be tracked:

| Target | Value | Notes |
|--------|-------|-------|
| Upload-to-queue latency (p95) | `<= 30s` | For 100-file batch under representative load |
| Dispatch success rate | `>= 99%` | Non-vacuous; excludes zero-job scenarios |
| Mixed-model-type handling | Per-file | Each file classified individually; mixed types allowed in batch |
