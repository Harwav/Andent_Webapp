# Andent Web PRD

> **Status:** Phase 0 complete (2026-04-18). Active product — governs Phase 1 through production.

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

## Approved Phase 0 Scope

Phase 0 delivered classification intake (FastAPI server, STL upload, classification table, editable Model Type/Preset). **Complete as of 2026-04-18.** See `Andent/99_archive/phase-0-build-today.md` for full detail.

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

## Recommended Handoff

Recommended next step: `$ralplan`

Suggested invocation:

```text
$plan --consensus --direct .omx/specs/deep-interview-andent-web-auto-prep-prd.md
```

Alternative handoffs:

- `$autopilot .omx/specs/deep-interview-andent-web-auto-prep-prd.md`
- `$ralph .omx/specs/deep-interview-andent-web-auto-prep-prd.md`
- `$team .omx/specs/deep-interview-andent-web-auto-prep-prd.md`

## Residual Risks

- The spec sets a clear straight-through target, but it does not yet define:
  - upload-to-queue latency target
  - printer dispatch success-rate target
  - handling rules for mixed-model-type uploads
- Those should be tightened during planning, not reopened as intent ambiguity.
