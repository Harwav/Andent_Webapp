# RALPLAN PRD: Andent V2 Unattended Dispatch

## Metadata
- Created: 2026-04-10T12:35:00Z
- Source brief: `.omx/specs/deep-interview-andent-v2-mvp-prd.md`
- Source transcript: `.omx/interviews/andent-v2-mvp-prd-20260410T120609Z.md`
- Planning mode: `ralplan` / consensus
- Consensus status: approved

## RALPLAN-DR Summary

### Principles
- Preserve case cohesion wherever workflow/material compatibility allows it.
- Default to unattended success-path automation in V2; humans handle exceptions.
- Keep dispatch policy explicit: virtual auto-dispatch by default, real auto-dispatch opt-in only.
- Treat V2 as distinct from the older V1 approval-first model.
- Reuse the existing Andent/FormFlow Dent pipeline where possible, but do not keep V1 compatibility as a planning constraint.

### Decision Drivers
- Brownfield leverage: queue intake, classification, build planning, `.form` export, screenshots, and dispatch plumbing already exist.
- Throughput goal: remove the approval-only bottleneck for successful cases.
- Workflow incompatibility: Splint material/layer rules conflict with Ortho/Tooth inside a single `.form`.

### Viable Options
| Option | Summary | Pros | Cons |
| --- | --- | --- | --- |
| A. Distinct V2 path reusing shared brownfield modules | Treat V2 as its own Andent planning/implementation target while reusing current processing pieces | Clean separation from V1, no legacy-governance overhead, still brownfield-friendly | Requires deliberate cutover work |
| B. Versioned V2 policy on the existing pipeline | Add site-level `andent_policy=v2` behavior to the current Andent path | Lower short-term code churn | Keeps V1 compatibility complexity that the user no longer wants |
| C. Keep approval-first and add optional auto-dispatch action | Preserve old path and add a manual acceleration step | Lowest operational risk | Misses the core unattended-V2 objective |

### Decision
Choose **Option A**: a distinct Andent V2 path that reuses shared brownfield modules without preserving V1 as an in-scope fallback.

### Invalidated Alternatives
- Option B rejected because the user no longer wants V2 constrained by V1-era fallback/governance machinery.
- Option C rejected because it does not satisfy the V2 product goal of exception-only human handling.

## ADR

### Decision
Treat Andent V2 as a distinct successor path from V1 while reusing existing FormFlow Dent processing modules where they already fit.

### Drivers
- Existing code already supports most of the needed behavior.
- V2's real product change is unattended routing and workflow splitting rules, not a new product shell.
- Real-printer automation must remain explicitly controlled.

### Alternatives Considered
- Versioned V2 policy on the existing pipeline
- Approval-first default with manual auto-dispatch action

### Why Chosen
This keeps the implementation brownfield-friendly while cleanly separating V2 from V1, which the user is preparing to discard.

### Consequences
- V1 fallback compatibility is no longer a planning requirement for V2.
- Mixed `Splint + Ortho/Tooth` single-case inputs are automated via separate workflow-specific `.form` files for the same case.
- Deterministic naming details are implementation constraints: sort case IDs lexicographically and use a consistent site-local date.

### Follow-ups
- Define the exact V2 entrypoint/config surface in the app so it is distinct from the older V1 flow.
- Validate best-effort tooth supports on representative Andent sample data.

## Product Intent
Turn Andent V2 into a largely unattended preparation engine that ingests queued folders, prepares valid `.form` jobs automatically, emits screenshots beside outputs, and dispatches successful builds without human checkpoints in the default virtual-printer path.

## Scope

### In Scope
- Separate V2 path/config from the older V1 approval-first flow
- Default virtual auto-dispatch for successful V2 jobs
- Opt-in real-printer auto-dispatch
- `.form` plus screenshot output for successful builds
- Machine-readable naming: `{YYYYMMDD}_{workflow}_{caseIds}`
- Mixed `Ortho + Tooth` case cohesion inside one `.form`
- Mixed single-case `Splint + Ortho/Tooth` splitting into separate workflow-specific `.form` files
- Best-effort tooth support heuristics with failure-to-exception routing
- Explicit manual-review routing for invalid or failed automation cases

### Out Of Scope
- Preserving V1 approval-first compatibility as a delivery constraint
- Strict geometric proof of tooth support touchpoint height

## Workflow Rules

### Ortho
- Flat on build platform
- Hollow automatically
- Arrange automatically
- `Precision Model`
- `50 micron`

### Tooth
- Auto-classify
- Auto-support with best-effort lower-region targeting
- `Precision Model`
- `50 micron`
- If support generation fails or yields zero supports, route to manual review
- May share a `.form` with `Ortho`

### Splint
- Auto-classify
- Tooth profiles facing up
- `15 deg` tilt
- Auto-support
- Arrange automatically
- `Dental LT Clear V2`
- `100 micron`
- Must not share the same `.form` with `Ortho` or `Tooth`

## Packing And Exception Rules
- Files from the same case should stay on the same `.form` when workflow/material constraints are compatible.
- One case normally stays on one `.form`.
- One `.form` may contain more than one case if they fit and workflow/material constraints are compatible.
- Mixed `Ortho + Tooth` cases remain in one `.form`.
- Any single case containing `Splint + Ortho/Tooth` is split into separate workflow-specific `.form` files for that same case:
  - one `Splint` `.form`
  - one combined `Ortho/Tooth` `.form`
- Other exception triggers:
  - classification ambiguity
  - support generation failure
  - zero supports where supports are required
  - export failure
  - scene/render failure
  - cannot-fit cases

## V2 Separation
- V2 is planned and implemented as a distinct Andent successor path from V1.
- V2 does not need approval-first fallback behavior to remain a release constraint.
- Shared modules may be reused, but V2 rules should not be weakened to preserve V1 semantics.
- Real-printer auto-dispatch remains a separate explicit opt-in under V2.

## Acceptance Criteria For Execution
- Successful V2 jobs generate `.form` and screenshot outputs with `{YYYYMMDD}_{workflow}_{caseIds}` naming.
- Successful V2 jobs auto-dispatch to virtual printers by default.
- Real printers auto-dispatch only when explicit opt-in is enabled.
- V2 runs as a distinct path from V1 rather than a V1 compatibility mode.
- Same-case artifacts stay together unless a single case contains `Splint + Ortho/Tooth`, which must be split by workflow family.
- Mixed `Ortho + Tooth` cases remain in one `.form`.
- Mixed `Splint + Ortho/Tooth` single-case inputs generate separate `Splint` and `Ortho/Tooth` `.form` files.
- Ortho, Tooth, and Splint jobs resolve to their defined material/layer/orientation rules.
- Exception triggers route to manual review instead of dispatch.

## Implementation Plan

### Phase 1. V2 Separation
- Define the V2 entrypoint/configuration surface
- Decouple V2 planning and processing from V1 approval-first assumptions
- Keep reusable shared modules behind neutral interfaces

### Phase 2. Routing And Packing Rules
- Keep mixed `Ortho + Tooth` cohesive
- Add workflow-family split rule for `Splint + Ortho/Tooth`
- Preserve no-split semantics for all other compatible cases

### Phase 3. Output Semantics
- Enforce `.form` + screenshot sibling output
- Implement deterministic naming helpers

### Phase 4. Dispatch Path
- Enable default virtual auto-dispatch under V2
- Gate real-printer dispatch behind explicit opt-in
- Ensure exception items never dispatch

### Phase 5. Tooth Heuristic And Exceptions
- Replace proof-gated tooth automation with best-effort support generation
- Route failed support-generation outcomes to manual review

## Verification Path
- Unit tests for V2 separation, classification, case planning, naming, and exception triggers
- Integration tests for `.form` + screenshot output and dispatch gating
- Manual validation on Andent sample folders, including mixed-family edge cases
- Regression tests only where shared FormFlow Dent behavior is still reused by V2

## Risks And Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Unintended real-printer dispatch | Production-side operational risk | Separate explicit opt-in gate plus tests |
| Mixed Splint cases processed incorrectly | Wrong material/layer output | Explicit workflow-family split rule with tests |
| Tooth heuristic produces fragile results | Print quality regressions | Failure-to-exception routing and sample-data validation |
| V1/V2 transition confusion during cutover | Misaligned operator expectations | Treat V2 artifacts/docs as separate and stop designing around V1 fallback |

## Suggested Execution Lane
- Preferred: `$ralph`
  - One owner can carry the V2 separation, routing, regression, and verification work sequentially.
- Secondary: `$team`
  - Use only if you want parallel lanes after policy/governance boundaries are accepted.

## Available Agent Types Roster
- `planner`
- `architect`
- `critic`
- `executor`
- `debugger`
- `test-engineer`
- `verifier`
- `code-reviewer`

## Staffing Guidance

### If Using `$ralph`
- One execution lane covering V2 separation, processing integration, regression tests, and manual verification evidence.

### If Using `$team`
- Lane 1: V2 separation/config and settings wiring
- Lane 2: workflow planning/packing and exception routing
- Lane 3: output naming, artifact generation, and dispatch gating
- Lane 4: regression and integration test expansion

## Reasoning Guidance By Lane
- V2 separation and routing: `high`
- Packing/exception semantics: `high`
- Output naming and artifacts: `medium`
- Dispatch gating: `medium`
- Regression and verification: `medium`
