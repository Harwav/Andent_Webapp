# Andent V2 Build Quality Improvement Plan

> **Context:** This improvement is planned for the Andent Web pipeline. It was originally scoped against the desktop app but will be implemented as part of the web product.

## Scope

This revision reflects your two constraints:

1. Overlap / print validation should be corrected automatically, not handled as a fail-closed operator path.
2. Mixed `ortho-tooth` must take the best path only: tooth-only supports in one unattended build, with no fallback behavior that still produces wrong output.

This plan remains limited to the Andent V2 path. It does not change the standard FormFlow Dent workflow.

## Requirements Summary

- Preserve Andent-specific behavior under `Andent V2 unattended mode`.
- Keep standard FormFlow Dent batching untouched.
- Keep case cohesion rules.
- Never generate supports on ortho models in mixed `ortho-tooth` builds.
- Use automatic layout repair so unattended output does not save overlapping / invalid scenes.
- Improve packing quality so borderline cases like `8425357` are merged when they truly fit.
- Record why a case stayed in a later build when it does not fit.

## Grounded Findings

### 1. Mixed `ortho-tooth` builds currently trigger scene-wide support generation

Evidence:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py:182`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py:186`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py:326`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py:1253`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py:1259`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py:786`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py:813`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\api_client.py:1142`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\api_client.py:1156`

Current behavior:

- Mixed `ortho + tooth` resolves to one `ortho_tooth` build with `requires_supports=True`.
- During processing, any build with `requires_supports=True` runs `_run_tooth_support_workflow(...)`.
- `ApiClient.auto_support_scene(...)` defaults to `models: 'ALL'`.

Consequence:

- In a mixed `ortho-tooth` scene, support generation is scene-wide rather than tooth-only.
- This directly explains why ortho models received supports in the live output.

### 2. The Local API already supports model-scoped support and model-scoped auto-layout

Evidence from the bundled Formlabs Local API spec:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:2840`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:2872`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:2909`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:3073`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:2929`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\docs\Formlabs Local API (0.9.11).json:3031`

Confirmed capability:

- `POST /scene/{scene_id}/auto-support/` accepts `models: [...]`, not just `ALL`.
- `POST /scene/{scene_id}/auto-layout/` also accepts `models: [...]`.

Consequence:

- We do not need a fallback product decision here.
- The best path is implementable: support only tooth model IDs, then run whole-scene layout repair after supports.

### 3. The packer is heuristic, pre-layout, and STL-dimension based

Evidence:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\batch_optimizer.py:195`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\batch_optimizer.py:255`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py:283`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py:313`

Current behavior:

- Packing is decided before scene import/layout.
- The fit decision uses a shelf heuristic on raw STL dimensions, not the final arranged scene or support-expanded footprint.

Observed effect on `Test Data 2`:

- The current planner keeps:
  - `10936643 + 8424903 + 8424921` in build 1
  - `10936926 + 8425357` in build 2
- A direct probe showed the current optimizer rejects adding either `10936926` or `8425357` to the first build under the current heuristic.

Consequence:

- The split is deterministic, but it is still only a heuristic.
- It can reject a case that might fit after real layout.

## Decision Drivers

1. The unattended output must be corrected automatically rather than saved in a known-bad state.
2. Mixed `ortho-tooth` must stay combined and still produce tooth-only supports.
3. Andent-specific fixes must not regress the standard workflow path.
4. Throughput matters, but packing decisions must reflect actual layout reality for borderline merges.

## Recommendation

Approve this single-path implementation:

1. Keep mixed `ortho-tooth` in one build.
2. Use model-scoped `auto-support` for tooth models only.
3. Run an auto-layout repair loop after supports are generated so the final scene passes print validation automatically.
4. Upgrade the planner so borderline merge candidates use a scene-aware fit probe before being split into a second build.

This is the best-path plan. It does not rely on manual-review fallback for the issues you called out.

## Target Workflow After Improvement

### Mixed `ortho-tooth`

1. Import all models into one scene.
2. Run `auto-layout` on the whole scene.
3. Identify tooth model IDs from the build plan.
4. Run `auto-support` on tooth model IDs only.
5. Run auto-layout repair with `allow_overlapping_supports=false`.
6. If validation still reports critical layout/support issues:
   - rerun whole-scene auto-layout with a bounded repair strategy
   - increase model spacing incrementally between attempts
7. Save `.form` and screenshot only after the repaired scene validates cleanly.

Expected result:

- Ortho models remain support-free.
- Tooth parts get supports.
- Auto-layout resolves collisions introduced by supports before export.

### Borderline packed builds

1. Keep the current heuristic as a fast first pass.
2. When a candidate case is rejected against an existing build by the heuristic, run a scene-aware fit probe:
   - import current build + candidate case into a temporary scene
   - run auto-layout
   - if tooth models exist, support the tooth subset and repair layout again
   - run print validation
3. Merge the candidate into the earlier build if the temporary scene validates cleanly.
4. If it still does not fit, keep it in a later build and record the explicit reason.

Expected result:

- `8425357` joins the first `.form` if it truly fits after real layout.
- If it still stays separate, the reason is grounded in a live-fit probe rather than a shelf estimate.

## Acceptance Criteria

1. Mixed `ortho-tooth` builds do not leave supports on ortho models.
2. Mixed `ortho-tooth` builds stay combined in one `.form` and still pass unattended validation after the repair loop.
3. The unattended path uses auto-layout repair so overlap-related validation issues are corrected before export rather than exported as-is.
4. For `Test Data 2`, the planner either:
   - places `8425357` into the first build if the live-fit probe validates it, or
   - keeps it in a second build and records an explicit reason based on the probe outcome.
5. Saved Andent `.form` files and screenshots are produced only after the repaired scene validates cleanly.

## Implementation Steps

### 1. Preserve per-model workflow membership in the Andent build plan

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py`

Changes:

- Extend `BuildPlan` to keep model membership metadata by file path and later by imported model ID:
  - tooth members
  - ortho members
  - splint members
- Preserve enough information for processing to target only tooth models during support generation.

### 2. Add model-scoped support generation for mixed `ortho-tooth`

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\api_client.py`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py`

Changes:

- Extend `ApiClient.auto_support_scene(...)` to accept explicit `models: [...]`.
- After scene import, map imported scene models back to build-plan members.
- In mixed `ortho-tooth` builds:
  - call `auto_support_scene(scene_id, payload={"models": tooth_model_ids, ...})`
- In tooth-only builds:
  - keep the scene-wide behavior if every model is a tooth.

### 3. Add auto-layout repair after support generation

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\api_client.py`

Changes:

- Add an Andent-specific repair loop that runs after supports are generated.
- Use `auto-layout` with:
  - `allow_overlapping_supports=false`
  - the current model spacing
- If validation still reports critical issues:
  - retry with a bounded number of repair passes
  - always on the whole scene
  - increase spacing between attempts

Goal:

- Make overlap / collision correction part of the unattended path rather than a post-hoc operator decision.

### 4. Add a scene-aware fit probe for candidate build merges

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\processing_controller.py`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\api_client.py`

Changes:

- Keep the current `BatchOptimizer` as a fast first pass.
- When the heuristic rejects a case against an existing build, run a temporary Andent-only probe scene:
  - import current build + candidate case
  - auto-layout
  - if needed, generate tooth-only supports
  - auto-layout repair
  - validate
- If probe passes, merge the candidate into the earlier build.
- If probe fails, keep the split and record the probe-backed reason.

### 5. Add explicit split diagnostics

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\andent_planning.py`

Changes:

- Record why a case did not join an earlier build:
  - max file-count cap
  - heuristic rejection
  - live-fit probe failed after repair
- Surface this reason in planning diagnostics and any operator-facing review artifact.

### 6. Add targeted regression and fixture-based tests

Files:

- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\tests\test_andent_workflow.py`
- `D:\Marcus\Desktop\FormFlow_Dent\FormFlow_Dent\tests\test_processing_controller_regression.py`

Tests:

- mixed `ortho-tooth` calls `auto_support_scene` with tooth-only model IDs
- mixed `ortho-tooth` runs auto-layout repair after support generation
- repaired scenes must validate before artifact save
- planner promotes `8425357`-style candidates into an earlier build when live-fit probe succeeds
- planner records explicit split reason when live-fit probe fails

## Risks and Mitigations

### Risk: Model-to-scene ID mapping may be ambiguous after import

Mitigation:

- Match by imported file name / original file path from scene metadata immediately after import.
- Add regression tests around mixed `ortho-tooth` scenes with repeated file naming patterns.

### Risk: Layout repair loops increase processing time

Mitigation:

- Use the current heuristic as the first filter.
- Run repair loops only for Andent V2.
- Use bounded retries with incremental spacing rather than an unbounded search.

### Risk: Re-layout after supports may slightly reposition models

Mitigation:

- This is acceptable for the Andent unattended objective because case-relative placement inside a shared build is not clinically constrained.
- The repair loop should prioritize valid non-overlapping builds over preserving the first rough arrangement.

## Verification Plan

1. Re-run `Test Data 2` and confirm:
   - no ortho supports in mixed `ortho-tooth`
   - the exported scenes pass validation cleanly
   - `8425357` joins the first build if it truly fits after real layout
2. Re-run the current workflow fixtures:
   - `01_ortho_happy`
   - `02_splint_happy`
   - `03_tooth_guard`
   - mixed `ortho-tooth`
   - mixed `splint + ortho/tooth`
3. Re-run focused regressions for:
   - model-scoped support workflow
   - auto-layout repair behavior
   - scene-aware merge probing

## Approved Direction

Approved repair strategy:

- go straight to whole-scene relayout after supports

This is now the locked implementation path for the Andent V2 build-quality fix.
