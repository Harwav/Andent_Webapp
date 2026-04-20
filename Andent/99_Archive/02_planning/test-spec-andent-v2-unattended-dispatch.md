# Test Spec: Andent V2 Unattended Dispatch

## Metadata
- Created: 2026-04-10T12:35:00Z
- Source plan: `Andent/02_planning/prd-andent-v2-unattended-dispatch.md`
- Source brief: `.omx/specs/deep-interview-andent-v2-mvp-prd.md`

## Test Strategy
Prove the separate Andent V2 unattended path in layers while only regression-testing shared reused behavior:
- unit tests for V2 entry behavior, planning rules, naming, and exception triggers
- integration tests for artifact output and dispatch gating
- manual validation for mixed-family and cutover scenarios

## Scope Under Test
- V2 separation from the older V1 approval-first path
- workflow classification
- case cohesion and packing rules
- mixed-family workflow splitting
- `.form` and screenshot output semantics
- virtual and real printer dispatch gates
- shared brownfield regression where V2 reuses existing modules

## Test Categories

### 1. Separation Tests For V2
- V2 path/config is distinct from the older V1 approval-first path.
- V2 unattended behavior does not depend on a V1 fallback toggle.
- Shared reused modules still behave correctly when invoked by the V2 path.

### 2. Unit Tests: Dispatch Defaults
- Virtual auto-dispatch is on by default in V2.
- Real-printer opt-in remains false by default in V2.

### 3. Unit Tests: Classification And Workflow Resolution
- `Ortho`, `Tooth`, and `Splint` artifacts still classify deterministically.
- Mixed `Ortho + Tooth` within one case remains automatable.
- Mixed `Splint + Ortho/Tooth` within one case is split into separate workflow-specific outputs.
- Classification ambiguity routes to manual review.

### 4. Unit Tests: Packing And Case Cohesion
- One compatible case never splits across multiple `.form` files.
- Multiple compatible cases may share one `.form`.
- Mixed `Ortho + Tooth` case stays in one `.form`.
- Mixed `Splint + Ortho/Tooth` case produces:
  - one `Splint` `.form`
  - one `Ortho/Tooth` `.form`
- Cannot-fit single case routes to manual review.

### 5. Unit Tests: Output Naming
- Successful outputs follow `{YYYYMMDD}_{workflow}_{caseIds}`.
- Joined `caseIds` are deterministic via lexicographic ordering.
- Date token uses the configured site-local day consistently.
- Screenshot uses the same job-name base as the `.form`.

### 6. Unit Tests: Tooth Heuristic Exceptions
- Tooth support generation success allows unattended continuation.
- Tooth support generation failure routes to manual review.
- Zero-support result where supports are required routes to manual review.

### 7. Integration Tests: Artifact Output
- Successful V2 builds save a `.form`.
- Successful V2 builds save a sibling screenshot.
- Mixed `Splint + Ortho/Tooth` case saves separate sibling outputs for each workflow-specific `.form`.
- Export failure routes the case/build to manual review and prevents dispatch.

### 8. Integration Tests: Dispatch Gating
- Successful V2 builds auto-dispatch to virtual printers by default.
- Successful V2 builds do not auto-dispatch to real printers unless opt-in is enabled.
- Exception/manual-review items never dispatch.

### 9. Manual Validation Matrix
- Ortho-only case:
  - correct workflow
  - `.form` + screenshot output
  - virtual auto-dispatch under V2
- Tooth-only case:
  - support path invoked
  - success or explicit exception outcome
- Mixed Ortho+Tooth case:
  - one `.form`
  - stricter tooth behavior applied
- Splint-only case:
  - correct tilt/material/layer behavior
- Mixed Splint+Ortho/Tooth case:
  - one splint `.form`
  - one ortho/tooth `.form`
  - screenshots for both outputs
  - correct per-workflow material/layer settings

## Fixtures And Mocks
- Filename fixtures for `Ortho`, `Tooth`, `Splint`, ambiguous, and mixed-family cases
- Case-planning fixtures for:
  - one case
  - multi-case shared build
  - cannot-fit case
  - mixed `Ortho + Tooth`
  - mixed `Splint + Ortho/Tooth`
- Mocked API responses for:
  - scene creation
  - support generation
  - auto-layout/orientation
  - `.form` save
  - screenshot save
  - print/send operation
  - failure cases for export/render/support
- V2 config fixture state

## Exit Criteria
- V2 separation tests pass.
- Packing and mixed-family workflow-split tests pass.
- Artifact output and dispatch-gating integration tests pass.
- Manual validation confirms mixed `Splint + Ortho/Tooth` generates separate workflow-specific outputs.

## Known Risks To Track During Execution
- Tooth heuristics may still be operationally weak even when technically successful.
- Site-local date behavior for naming must be stable across workstations.
- Real-printer opt-in UX must stay clear in the separate V2 flow.
