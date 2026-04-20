# RALPLAN PRD: Andent MVP On FormFlow Dent

## Metadata
- Created: 2026-04-09T13:08:11Z
- Source brief: `.omx/specs/deep-interview-andent-mvp-prd.md`
- Customer draft: `Andent/PRD_andent_mvp.md`
- Planning mode: `ralplan` / consensus
- Consensus status: approved

## RALPLAN-DR Summary

### Principles
- Keep one product. Extend FormFlow Dent instead of creating a separate Andent fork.
- Preserve production safety over throughput. Unsafe or ambiguous cases must fail to review.
- Keep case cohesion hard. A single case may not be split across builds.
- Add policy layers, not scattered conditionals. Workflow rules should resolve before processing begins.
- Reuse current scene/export infrastructure wherever it already matches the desired outcome.

### Decision Drivers
- Brownfield leverage: current code already supports scene creation, batch `scan-to-model`, auto-layout, validation, `.form` export, and local printer coordination.
- Safety-critical tooth workflow: support behavior needs a conservative control surface and manual-review fallback.
- MVP boundary: approved output is a prepared build plus screenshot, not printer dispatch.

### Viable Options
| Option | Summary | Pros | Cons |
| --- | --- | --- | --- |
| A. Workflow-policy layer inside the existing app | Add artifact classification, case planner, workflow resolver, and approval artifact generation on top of current processing flow | Smallest conceptual jump, reuses current code, consistent with existing workflow-preset direction | Requires refactoring global `api_params` assumptions and aligner-only comments |
| B. Separate Andent-specific processing pipeline in the same repo | New isolated path for Andent jobs while leaving current flow mostly untouched | Lower short-term regression risk to current aligner flow | Duplicates logic, weakens long-term maintainability, harder to generalize |
| C. Separate Andent fork/app | Build a custom branch or app for this customer | Maximum isolation | Highest maintenance cost, breaks one-product direction, duplicates infrastructure |

### Decision
Choose **Option A**: add a first-class workflow-policy layer and case-aware build planner inside the existing FormFlow Dent application.

### Why Option A
- It matches the existing `Andent/PLAN_workflow-preset-variant.md` direction.
- The current architecture already has obvious seams:
  - scene creation via `app_gui._get_api_payload()`
  - processing orchestration via `ProcessingController.run_processing_loop()`
  - API operations via `ApiClient`
  - printer selection and output routing via existing controllers and settings
- The MVP needs workflow resolution and batching policy more than a brand-new product shell.

### Invalidated Alternatives
- Option B rejected because it would copy the core processing path and create two divergent batch engines.
- Option C rejected because the scope is workflow specialization, not a fundamentally separate product.

## ADR

### Decision
Implement the Andent MVP as a workflow-driven extension of the main FormFlow Dent app with four new internal layers:
- artifact classifier
- case-group planner
- workflow policy resolver
- approval artifact generator

### Drivers
- Existing app is already scene-centric and close to the ortho / implant path.
- Same-case build cohesion is a hard business rule.
- Tooth workflow requires a conservative safety envelope and explicit failure path.
- MVP ends at approval, not printing.

### Alternatives Considered
- Separate Andent-only pipeline in repo
- Separate forked customer app

### Why Chosen
This option minimizes product fragmentation while making the workflow-specific logic explicit and testable.

### Consequences
- Current “global mutable `api_params`” assumptions should be reduced.
- Processing must consume a resolved per-build workflow policy object, not raw settings alone.
- Approval output becomes a first-class outcome in the processing loop.
- The current code comments that frame the app as aligner-only will need to be updated carefully alongside behavior changes.

### Follow-ups
- Verify the exact Formlabs Local API behavior needed for screenshot generation and any support-related tuning.
- Decide whether the tooth-support lower-region rule can be represented entirely through API parameters or needs geometry-aware gating before support generation.

## Architect Review

### Steelman Antithesis
The biggest architectural risk is overloading the current aligner pipeline with too many workflow branches before extracting a clean policy seam. If the team simply sprinkles `if workflow == tooth_model` logic across `app_gui.py`, `processing_controller.py`, and `api_client.py`, the result will be brittle and hard to verify.

### Real Tradeoff Tension
- A stronger domain model upfront improves safety and maintainability.
- But too much abstraction too early slows MVP delivery.

### Synthesis
Introduce one bounded new abstraction:
- `ResolvedWorkflowPolicy`

That object should be the single place where workflow-specific behavior is expressed for a build:
- classification result
- case metadata
- scene settings strategy
- import/hollow/support/layout rules
- approval artifact requirements
- fail-to-review conditions

Everything else can remain close to current code structure for MVP.

## Critic Review

### Verdict
APPROVE

### Why
- Options are fair and bounded.
- The chosen architecture aligns with explicit customer constraints.
- Risks are preserved rather than hand-waved away.
- Acceptance criteria and test strategy are concrete enough to guide execution.

### Required Guardrails
- Do not claim support for exact tooth touchpoint height limiting until verified in implementation.
- Preserve a strict fail-to-review path for unsupported tooth cases and oversized cases.
- Keep current aligner behavior protected with regression tests before widening scope.

## Implementation Plan

### Phase 1. Domain And Persistence
Add workflow and case-planning domain objects without changing output behavior yet.

Deliverables:
- workflow types for:
  - ortho_implant
  - tooth_model
  - splint
  - manual_review
- `ResolvedWorkflowPolicy`
- case grouping metadata
- settings model extension for workflow/preset support

Likely touchpoints:
- `settings_manager.py`
- new module such as `workflow_policy.py`
- new module such as `artifact_classifier.py`
- new module such as `case_planner.py`

### Phase 2. Classification And Build Planning
Build deterministic classification and batching rules before touching the actual processing path.

Deliverables:
- filename-first classifier
- geometry-heuristic fallback classifier
- stable case-id extraction
- planner that:
  - keeps a case on one build
  - allows multi-case builds
  - fails oversized cases to manual review

Likely touchpoints:
- new classifier/planner modules
- `batch_optimizer.py` integration or wrapper logic
- tests with the Andent sample naming families

### Phase 3. Processing Policy Integration
Wire the resolved policy into the existing scene-processing flow.

Deliverables:
- change processing entrypoint so it receives resolved build plans, not raw folder batches only
- workflow-specific scene settings and import behavior
- support-operation hook for tooth workflows
- approval-mode branch that prepares artifacts and stops before print dispatch

Likely touchpoints:
- `processing_controller.py`
- `api_client.py`
- `app_gui.py`

### Phase 4. Approval Artifacts
Make approval a first-class output path.

Deliverables:
- prepared `.form` export path for approval
- screenshot export path
- review status surfaced in UI/reporting
- structured reasons for manual-review failures

Likely touchpoints:
- `api_client.py`
- `processing_controller.py`
- `app_gui.py`
- output/report helpers

### Phase 5. UI And Operator Experience
Expose workflow state and manual-review outcomes without adding full CAD tooling.

Deliverables:
- top-level workflow selection or workflow-aware mode display
- queue/build summaries grouped by case
- manual-review messaging for:
  - oversized single case
  - unsafe tooth support constraints
  - unsupported classification ambiguity

Likely touchpoints:
- `app_gui.py`
- sidebar/settings UI modules
- session output/reporting UI

## Concrete Work Items

### Workstream A. Introduce workflow policy resolution
- Define `ResolvedWorkflowPolicy`
- Resolve from:
  - artifact family
  - selected preset/workflow
  - printer/material settings source
- Stop reading ad hoc workflow assumptions directly from `settings.get('api_params')`

### Workstream B. Implement case-aware batch planning
- Add case extraction and grouping
- Build a planner that emits build units composed of one or more whole cases
- Add fail-to-review output for single cases that cannot fit

### Workstream C. Add support-capable API surface
- Add explicit `auto_support_scene()` client support in `api_client.py`
- Add screenshot export client support in `api_client.py`
- Keep those operations separate from the current aligner-only assumptions

### Workstream D. Add approval-mode processing
- Reuse save/export flow
- Replace “print or save only” binary with a third explicit outcome:
  - prepare_for_approval
- Emit:
  - `.form`
  - screenshot
  - review metadata

### Workstream E. Manual-review pipeline
- Standardize reasons and operator messaging
- Do not silently skip or partially process unsafe cases

## Acceptance Criteria For Execution
- The system classifies Andent sample artifacts into the target workflow families with explainable, testable rules.
- Case grouping is deterministic and prevents one case from spanning multiple builds.
- A case that exceeds single-build capacity becomes a manual-review item, not a split plan.
- Ortho / implant builds resolve to the specified flat, support-free workflow.
- Tooth builds only proceed automatically when their support policy passes the safety gate.
- Approval preparation produces both `.form` and screenshot artifacts.
- No automatic printer dispatch occurs on the Andent MVP path.
- Existing aligner behavior remains regression-protected.

## Verification Plan
- Unit tests for classification, case extraction, workflow resolution, and planner outcomes
- Integration tests around processing policy selection and approval-artifact generation
- Manual validation with the Andent sample set
- Explicit proof for:
  - oversized-case failure
  - mixed multi-case build success
  - tooth-model manual-review fallback

## File Touchpoints
- `settings_manager.py`
- `app_gui.py`
- `processing_controller.py`
- `api_client.py`
- `batch_optimizer.py`
- new modules for workflow, classification, and planning

## Risks And Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Tooth support rule cannot be enforced precisely through available API parameters | Unsafe output or blocked workflow | Treat exact lower-region support as a gated capability; fail to review when confidence is low |
| Workflow logic leaks into many unrelated files | Maintenance cost and regressions | Centralize in `ResolvedWorkflowPolicy` and build planner modules |
| Current aligner behavior regresses | Existing customers impacted | Add regression tests before widening processing behavior |
| Screenshot API path is unimplemented in current client | Approval flow incomplete | Add dedicated `save_screenshot` client method early and prove it with integration validation |

## Suggested Execution Lane
- Preferred: `$ralph`
  - Reason: this work is sequentially coupled and benefits from one owner carrying behavior-preserving refactors plus verification.
- Secondary: `$team`
  - Use only if you want parallel lanes after the domain model is agreed.
  - Suggested split:
    - Lane 1: classifier + case planner
    - Lane 2: workflow policy + processing integration
    - Lane 3: approval artifact UX + reporting

## Available Agent Types Roster
- `architect`
- `debugger`
- `executor`
- `verifier`
- `test-engineer`
- `code-reviewer`
- `critic`
- `planner`

## Reasoning Guidance By Lane
- Workflow and policy design: high
- Batch planner and failure semantics: high
- API client additions: medium
- UI wiring and reporting: medium
- Verification and regression testing: medium
