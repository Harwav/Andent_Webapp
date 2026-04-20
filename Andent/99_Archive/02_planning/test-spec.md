# Test Spec: Andent MVP On FormFlow Dent

## Metadata
- Created: 2026-04-09T13:08:11Z
- Source plan: `.omx/plans/prd-andent-mvp.md`
- Source brief: `.omx/specs/deep-interview-andent-mvp-prd.md`

## Test Strategy
Protect existing aligner behavior first, then prove the new Andent-specific workflow logic in layers:
- unit tests for classification, grouping, policy resolution, and failure logic
- integration tests for processing-path branching and artifact generation
- manual validation against real customer samples

## Scope Under Test
- artifact classification
- case-id extraction
- case-aware build planning
- workflow policy resolution
- approval artifact generation
- manual-review gating
- regression safety for existing aligner flow

## Test Categories

### 1. Regression Tests For Existing Behavior
- Existing aligner/default workflow still imports, auto-layouts, validates, and exports `.form` successfully.
- Existing settings files with only `api_params` still load without data loss.
- Existing save-only and save-form flows still work when Andent workflow mode is unused.

### 2. Unit Tests: Classification
- Filename pattern classifies:
  - `UnsectionedModel_UpperJaw` as model
  - `Tooth_46` as tooth model
  - `Antag` as antagonist
  - `modelbase` as model base
  - `modeldie` as model die
  - `bitesplint_cad` as splint
- Geometry fallback reclassifies ambiguous names conservatively.
- Unknown or conflicting signals return a review-required classification instead of a false-positive workflow.

### 3. Unit Tests: Case Extraction
- Case IDs are derived correctly from:
  - `YYYYMMDD_CASEID_...`
  - `YYYY-MM-DD_BATCH-SEQ-CASEID_...`
  - `CASEID_YYYY-MM-DD_...`
  - `CASEID_...`
- Related files from the same case map to the same case group.
- Ambiguous filenames without a stable case token fail to manual review.

### 4. Unit Tests: Build Planning
- One case with multiple artifacts produces one build unit.
- Multiple small cases can share one build unit.
- One oversized case fails to manual review rather than splitting.
- Planner never emits two build units containing the same case.

### 5. Unit Tests: Workflow Policy Resolution
- Ortho / implant policy resolves to:
  - no supports
  - `50 micron`
  - flat-on-platform expectations
- Tooth policy resolves to:
  - support-required
  - safety-gated lower-region constraint
  - fail-to-review fallback
- Splint policy resolves to:
  - dental-workspace-preferred path
  - approval-artifact requirement

### 6. Integration Tests: API Client
- `create_scene()` still works with standard scene settings.
- New support-operation wrapper succeeds against mocked Local API responses.
- New screenshot-export wrapper writes an image file to disk.
- `.form` export and screenshot export can both run for the same prepared scene.

### 7. Integration Tests: Processing Controller
- Resolved build plans can enter the processing loop without relying on ad hoc folder batching alone.
- Approval-mode path exports `.form` and screenshot and does not dispatch to printers.
- Tooth-model builds that fail the support safety gate exit as manual-review items.
- Oversized single-case plans exit as manual-review items before scene execution.

### 8. UI And Operator Flow Tests
- Workflow selection or workflow-aware mode display updates the run configuration correctly.
- Manual-review cases surface a clear reason.
- Approval-ready cases surface output artifact locations clearly.

## Manual Validation Matrix

### Dataset
Use `/Users/marcus.liang/Desktop/BM/20260409_Andent_Matt`

### Manual Runs
- Run a normal ortho / implant case from the sample set and confirm:
  - correct classification
  - single-build preparation
  - `.form` export
  - screenshot output
- Run a tooth-model case and confirm:
  - tooth workflow selected
  - support path invoked or explicitly failed to review
  - no printer dispatch
- Run a splint case and confirm:
  - splint workflow selected
  - approval artifacts generated
- Run a mixed multi-case folder and confirm:
  - cases may share a build
  - no case is split
- Run or simulate an oversized case and confirm:
  - planner fails it to manual review

## Mocks And Fixtures
- Local API fixture responses for:
  - scene creation
  - batch `scan-to-model`
  - auto-layout
  - print validation
  - screenshot save
  - `.form` save
  - auto-support
- Sample filename fixtures spanning all observed naming families
- Geometry metadata fixtures for ambiguous STL classifications

## Exit Criteria
- All new unit tests pass.
- Regression tests for current default flow pass.
- Approval-mode integration tests pass.
- Manual validation confirms:
  - same-case cohesion
  - no auto-dispatch
  - manual-review fallback for unsafe or oversized cases

## Known Gaps To Track During Execution
- Exact proof for the lower `7-8 mm` touchpoint rule may require additional geometry-aware gating beyond raw Local API parameters.
- Dental Workspace parity for splints must be validated against the exact Local API behavior available in the installed PreFormServer version.
