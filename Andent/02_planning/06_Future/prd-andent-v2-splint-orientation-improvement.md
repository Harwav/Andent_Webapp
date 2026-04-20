# RALPLAN PRD: Andent V2 Splint Orientation Improvement

> **Context:** This improvement is planned for the Andent Web pipeline. It was originally scoped against the desktop app but will be implemented as part of the web product.

## Metadata
- Created: 2026-04-11T00:00:00Z
- Source plan: `Andent/02_planning/prd-andent-v2-unattended-dispatch.md`
- Source evidence: `Andent/02_planning/verification_test_data_2_build_quality_20260410/verification-summary.json`
- Planning mode: `ralplan` / consensus
- Consensus status: approved

## RALPLAN-DR Summary

### Principles
- Splint preparation must obey the V2 workflow contract exactly, not approximately.
- Orientation quality matters more than raw unattended throughput for splints.
- Use scene-level verification after every orientation/support mutation.
- Keep the fix isolated to the Andent V2 splint path.
- Prefer deterministic repair loops over operator cleanup.

### Decision Drivers
- Current splint preparation can satisfy the nominal call order while still producing the wrong physical orientation outcome.
- Splints have stricter material, tilt, and support-touchpoint requirements than Ortho or Tooth.
- The user explicitly wants the best automated path, not a degraded fallback.

### Viable Options
| Option | Summary | Pros | Cons |
| --- | --- | --- | --- |
| A. Tighten the existing splint scene pipeline with stronger orientation verification and repair loops | Reuse the current V2 splint path, but make it prove the required orientation/material/layout outcome before export | Smallest brownfield diff, preserves current architecture, directly targets the failure | Requires better scene-model inspection and stricter verification logic |
| B. Create a separate splint-only processor lane | Build a bespoke splint engine with custom sequencing and packing behavior | Maximum isolation, easier to reason about splints separately | Higher maintenance cost, duplicates shared pipeline logic |
| C. Keep current pipeline and rely on manual review for bad splints | Preserve the existing workflow and escalate more often | Lowest implementation effort | Does not satisfy the unattended-V2 product goal |

### Decision
Choose **Option A**: strengthen the existing Andent V2 splint pipeline so it validates the real scene outcome against the V2 splint rules before export.

### Invalidated Alternatives
- Option B rejected because the failure shape is inside the current splint scene workflow, not evidence that a second pipeline is needed.
- Option C rejected because the user explicitly wants the best automated path, not a safe-but-weaker manual fallback.

## ADR

### Decision
Keep splints on the current Andent V2 brownfield path, but harden the splint-specific orientation/support/layout pipeline until it can enforce the V2 splint contract.

### Drivers
- Splints already have a distinct policy in `andent_planning.py`.
- `processing_controller.py` already has a dedicated `_apply_splint_orientation_workflow(...)`.
- The gap is quality of verification and repair, not absence of a splint branch.

### Alternatives Considered
- Separate splint-only pipeline
- Manual-review-first splint policy

### Why Chosen
The current code already has the right extension points. Tightening them gives the smallest reviewable change that directly addresses the observed splint misorientation.

### Consequences
- Splint export becomes more strict than today.
- Some splint scenes may take longer because repair loops run after orientation/support/layout.
- Splint-specific tests must expand beyond simple API-call ordering and assert scene outcome quality.

### Follow-ups
- Update the Andent flowchart if the splint pipeline shape changes materially.
- Re-run live splint fixtures after implementation and compare screenshots to the target orientation intent.

## Problem Statement
The current Andent V2 splint workflow does not yet reliably produce the intended real-world result:
- tooth profile facing up
- `15 deg` tilt
- `Dental LT Clear V2`
- `100 micron`
- auto support generation
- auto layout

The existing path calls splint-specific APIs, but the observed result indicates that the scene can still end up improperly oriented.

## Product Intent
Make the Andent V2 splint path reliably produce printable splint scenes that honor the V2 PRD's material, tilt, support, and layout rules without weakening the unattended automation goal.

## Scope

### In Scope
- Splint-only Andent V2 processing behavior
- Splint scene payload resolution for `Dental LT Clear V2` and `0.1 mm`
- Splint orientation verification beyond simple API call order
- Whole-scene auto-layout after splint orientation and after splint support generation
- Scene validation before export
- Splint-specific repair/retry logic when orientation or support outcome is insufficient
- Splint live-verification artifacts and regression coverage

### Out Of Scope
- Reworking Ortho or Tooth behavior
- Changing mixed-case split rules
- Building a second independent splint pipeline
- Real-printer hardware validation

## Required Splint Outcome
- Material resolves to `Dental LT Clear V2`
- Layer thickness resolves to `0.100 mm`
- Splint tooth profile faces upward
- Scene carries a meaningful tilt signal equivalent to the intended `15 deg` preparation
- Auto-support completes
- Auto-layout completes after orientation and after supports
- Final scene passes print validation before export

## Current Failure Shape
- The current splint path may succeed at:
  - `auto_orient`
  - `auto_layout`
  - `auto_support`
- But still fail the user's intended geometric outcome:
  - tooth-contact surface not clearly facing upward
  - tilt insufficient or unstable after layout/support mutation
  - support placement inconsistent with the intended splint presentation

## Acceptance Criteria For Execution
- Splint jobs resolve to `Dental LT Clear V2` and `0.100 mm`.
- Splint jobs run the splint-specific orientation path before export.
- Splint jobs run auto-layout after orientation and again after support generation.
- Exportable splint scenes show the tooth profile facing up in the generated preview.
- Exportable splint scenes show a stable tilted posture consistent with the V2 requirement.
- Splint support generation succeeds and remains present after the final relayout.
- Splint scenes pass print validation before `.form` and screenshot export.
- If a splint scene cannot achieve the required outcome after bounded repair, it routes to manual review instead of exporting a wrong `.form`.

## Implementation Plan

### Phase 1. Scene-Outcome Verification
- Replace the current conservative "not too flat" proxy with a stronger splint-scene verification pass.
- Compare initial vs final scene geometry and orientation after every splint mutation.
- Add model-level checks for:
  - support presence
  - final tilt signal
  - final build height / posture

### Phase 2. Splint Repair Loop
- Run:
  - splint auto-orient
  - whole-scene auto-layout
  - splint supports
  - whole-scene auto-layout
- If outcome still misses the required splint posture, retry with bounded repair parameters before export.
- Preserve `allow_overlapping_supports=False` through the repair path.

### Phase 3. Export Gate
- Do not export a splint `.form` or screenshot unless the final splint scene satisfies:
  - required material/layer settings
  - support presence
  - splint orientation verification
  - print validation

### Phase 4. Evidence And Regression
- Expand tests from call-order assertions to outcome-quality assertions.
- Add live verification on a representative splint folder with screenshot inspection.

## Verification Path
- Unit tests for splint policy resolution and required scene payload selection
- Integration tests for:
  - orientation -> layout -> support -> relayout ordering
  - support persistence after final relayout
  - failure to export when splint posture remains wrong
- Manual validation against real splint data with screenshot review

## Risks And Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| API orientation metadata is weaker than expected | Harder to prove tooth profile is facing up | Use multiple scene signals together: orientation, build-height change, support presence, preview inspection in live validation |
| Relayout after supports destabilizes the intended tilt | Good splints regress late in the pipeline | Re-verify after every relayout and keep the final export gate strict |
| Material resolution differs across printer families | Wrong resin/layer profile | Resolve required scene settings from printer/material presets and reject missing profile availability |

## Suggested Execution Lane
- Preferred: `$ralph`
  - One owner can tighten the splint scene workflow, extend tests, and collect live evidence sequentially.
- Secondary: `$team`
  - Use only if you want separate lanes for controller changes, scene-verification logic, and live-validation evidence.

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
- One lane covers splint controller hardening, test expansion, and live validation.

### If Using `$team`
- Lane 1: splint policy and scene-payload verification
- Lane 2: splint orientation/support/layout repair logic
- Lane 3: regression tests and live verification evidence

## Reasoning Guidance By Lane
- Splint scene verification: `high`
- Repair-loop sequencing: `high`
- Regression and live evidence: `medium`
