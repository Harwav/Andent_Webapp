# Form 4BL Build Layout Design

Date: 2026-04-21
Status: Implemented and repository-verified on 2026-04-21
Scope: Compatibility-aware mixed-preset build planning for Form 4BL handoff

## Summary

This design changes Andent Web from preset-only batching to compatibility-aware build planning for Form 4BL jobs.

Implementation note (2026-04-21): this design is now implemented in `app/services/preset_catalog.py`, `app/services/build_planning.py`, `app/services/print_queue_service.py`, and `app/services/planning_preview.py`. Repository verification passed with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q` (`187 passed`). Live PreFormServer/Formlabs acceptance validation remains a separate launch gate.

Implementation note (2026-04-23): the planner was further refined to make build selection printer-aware. The current repository now:

1. scales XY budgets by printer family instead of assuming one Form 4BL-sized budget for all builds
2. starts new `Form 4B` builds by attempting the largest `3` cases when at least `3` remain
3. starts new `Form 4BL` builds by attempting the largest `8` cases when at least `8` remain
4. continues descending by case priority until the first fit miss
5. then switches to smallest fillers

The fit signal remains heuristic and XY-budget-only. No live scene-fit probe was added in this refinement.

The planner must:

1. Keep each `case` intact. A case must never split across builds.
2. Allow mixed presets in one build only when they resolve to the same compatible `printer + resin + layer_height` family.
3. Preserve per-file preset application so PreFormServer receives the correct preset hint for each imported file.
4. Use a fast case-level XY packing heuristic that improves platform utilization without trying to replace PreFormServer as the true layout engine.
5. Keep planning latency bounded by using a greedy first pass and simple rollback instead of exhaustive search.

PreFormServer remains the final authority for actual scene layout, validation, and dispatch.

## Problem

The current repository groups ready rows by preset and sends each preset group as a separate scene. That is too coarse for the Form 4BL objective because:

1. Compatible presets that share the same resin and layer settings cannot currently share one build.
2. Batching by preset alone leaves platform capacity unused.
3. Preset handling is too build-wide for a future where one compatible scene may contain files that need different preset hints.
4. The current handoff flow has no case-aware packing heuristic, so it cannot deliberately improve fill rate while still preserving case cohesion.

The target is not a perfect global optimum. The target is a practical planner that increases parts per Form 4BL build while keeping planning time low and staying safe at the case boundary.

## Goals

1. Increase Form 4BL platform utilization relative to preset-only batching.
2. Keep `case` as the indivisible planning unit.
3. Allow compatible mixed presets in the same build.
4. Derive `printer`, `resin`, `layer_height`, and `requires_supports` from `preset_name` through one preset catalog.
5. Preserve exact per-file preset application at import time.
6. Use XY footprint estimation only. Z height is intentionally out of scope for this heuristic.
7. Use a bounded heuristic: largest/hardest-first seeding, then smallest-fit fillers.
8. Fall back by removing whole cases only when validation rejects a candidate build.

## Non-Goals

1. Compute a mathematically optimal packing solution.
2. Reimplement PreFormServer's layout solver inside Andent Web.
3. Split one case across multiple builds to improve utilization.
4. Mix presets that do not share the same compatible `printer + resin + layer_height` family.
5. Use Z-height-driven ranking for dental models in this planning pass.

## Core Planning Principle

Andent Web should estimate and group. PreFormServer should layout and validate.

That means the web app owns:

1. Case grouping.
2. Preset compatibility checks.
3. Case-level footprint estimation.
4. Build candidate construction.
5. Per-file preset-aware import manifests.

PreFormServer owns:

1. Scene import.
2. Real layout.
3. Validation.
4. Dispatch to the printer group.

## Compatibility Model

`preset_name` is the canonical input for preparation settings.

Andent Web should maintain a preset catalog that derives the following from each preset:

1. `printer`
2. `resin`
3. `layer_height`
4. `requires_supports`

Cases may share a build only if every file in those cases resolves to the same compatible `printer + resin + layer_height` family.

This allows:

1. Multiple presets in one build when they are operationally mixable.
2. Per-file preset differences to remain explicit.
3. Centralized compatibility logic instead of duplicated ad hoc checks.

## Planning Heuristic

The planning unit is `case`, not file.

For each case, Andent Web computes a 2D XY packing estimate based on the files in that case. The estimate should include:

1. Base XY footprint per file.
2. Support inflation for presets that require supports.
3. Case-level combined XY envelope after virtual case arrangement.
4. A difficulty score that ranks awkward or wide cases above compact ones.

The planner then works per compatibility pool:

### Phase 1: Seed With Largest/Hardest Cases

1. Sort cases by `difficulty desc`, then `footprint desc`.
2. Start a new build with the largest/hardest remaining compatible case.
3. Continue trying the next-largest compatible cases while they fit the remaining estimated XY budget.

This anchors the build with the cases that are hardest to place later.

### Phase 2: Fill With Smallest Cases

Once the next large case no longer fits, switch to filler mode:

1. Sort the remaining compatible cases from smallest to largest.
2. Add the smallest whole case that still fits the remaining estimated XY budget.
3. Repeat until no remaining whole case fits.

This uses small cases to fill the leftover gaps created by the larger anchor cases.

### Optional Bounded Improvement

If needed, the planner may run one small improvement pass before handoff:

1. Remove one medium case.
2. Test whether two or more smaller compatible cases produce better estimated utilization.
3. Keep the replacement only if total packed XY usage improves.

This pass must stay bounded. It is a local improvement step, not a broad search.

## Data Model

The planner should store four objects.

### 1. `FilePrepSpec`

One record per uploaded file:

1. `row_id`
2. `case_id`
3. `file_path`
4. `preset_name`
5. `xy_footprint_estimate`
6. `support_inflation_factor`

Derived through the preset catalog:

1. `printer`
2. `resin`
3. `layer_height`
4. `requires_supports`

### 2. `CasePackProfile`

One record per case:

1. `case_id`
2. `compatibility_key`
3. `preset_groups`
4. `total_xy_footprint`
5. `difficulty_score`
6. `file_count`

`preset_groups` maps each preset to the files inside the case that require it.

### 3. `BuildCandidate`

Temporary planning object:

1. `build_number`
2. `compatibility_key`
3. `case_ids`
4. `preset_groups_to_import`
5. `used_xy_budget`
6. `remaining_xy_budget`
7. `planning_status`

### 4. `BuildManifest`

Final handoff artifact:

1. build-level compatibility settings
2. ordered case list
3. ordered preset groups
4. per-file import instructions

This manifest is what drives grouped import into PreFormServer.

## Import Strategy

Within one compatible build, files should be imported by preset group so PreFormServer receives the correct hint for each file.

Import order:

1. import all files belonging to `preset A` using preset hint `A`
2. import all files belonging to `preset B` using preset hint `B`
3. continue until every file in the build has been imported
4. run `auto-layout`
5. run validation
6. if valid, dispatch to the printer group

This preserves per-file preset correctness without forcing one-preset-per-build behavior.

## Validation And Rollback

The planner should be aggressive on fill rate but conservative on failure handling.

For each candidate build:

1. construct the build manifest
2. import by preset group
3. run `auto-layout + validation`
4. if valid, lock the build
5. if invalid, remove the last-added whole case and retry

Fallback order:

1. remove the last-added filler case
2. retry validation
3. if still invalid, keep rolling back whole cases in reverse add order
4. if the seed case alone still fails, mark that case for explicit manual review
5. never split a case across two builds during rollback

This ensures invalid density assumptions are corrected without violating case cohesion.

## Why This Heuristic

The chosen heuristic is:

1. fast enough for routine automated planning
2. materially better than preset-only batching
3. more robust than a fixed "part count per Form 4BL" rule
4. easier to explain and debug than an opaque optimizer

It deliberately avoids:

1. blind large/small alternation from the start
2. exact brute-force search
3. reliance on one global capacity number for all dental models

The best practical sequence is:

1. largest/hardest-first seeding
2. then smallest-first fillers
3. then optional bounded swap improvement
4. then PreFormServer layout and validation

## Testing Requirements

Verification must focus on planning correctness, compatibility safety, and rollback behavior.

Required proof points:

1. compatible mixed presets can share one Form 4BL build
2. incompatible presets never mix
3. one case never splits across builds
4. `preset_name` is the single source of truth for derived prep settings
5. the planner follows largest-first seeding and smallest-first filler behavior
6. per-file preset hints are preserved during grouped import
7. validation failure ejects whole cases only
8. a seed case that fails alone is surfaced as an exception

Minimum test layers:

1. unit tests for preset catalog derivation and compatibility resolution
2. unit tests for case XY footprint scoring and difficulty ordering
3. unit tests for the build-construction heuristic
4. integration tests for build manifest generation and grouped import ordering
5. regression tests for rollback after failed validation

## Acceptance For This Design

This design is complete when implementation planning can answer:

1. how XY footprint estimates are calculated from STL dimensions and preset inflation rules
2. where the preset catalog lives and how it maps current UI presets to compatibility settings
3. how the planner persists `CasePackProfile`, `BuildCandidate`, and `BuildManifest`
4. which existing send-to-print path will own grouped import by preset
5. how validation failure will be surfaced in UI and database state
6. which tests will lock the no-case-splitting and mixed-compatible-preset guarantees

These are implementation-plan questions, not unresolved design questions.
