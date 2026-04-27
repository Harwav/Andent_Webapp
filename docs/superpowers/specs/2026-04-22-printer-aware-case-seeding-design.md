# Printer-Aware Case Seeding Design

Date: 2026-04-22
Status: Approved design for planner-driven build composition changes
Scope: `Andent_Webapp` build composition logic for printer-aware whole-case ordering

## Summary

This design updates Andent Web's build composition logic so case ordering matches the intended strategy:

1. Keep each case intact.
2. Start new builds with a printer-specific number of largest remaining cases.
3. Continue trying larger remaining cases first.
4. After the first descending-order fit failure, switch to smaller filler cases.
5. Continue using the current XY-budget heuristic as the fit signal.

This design applies to `Andent_Webapp` only. It must not modify `FormFlow_Dent`.

## Problem

The current build planner is case-preserving, but its selection loop does not express the intended operator strategy directly.

Current behavior in `app/services/build_planning.py`:

1. Choose the largest remaining case by the current priority metric.
2. Greedily take as many next-largest cases as fit.
3. Then scan smaller cases as fillers.

That is close to the intended behavior, but it does not encode the explicit startup rule the product now requires:

1. `Form 4B` builds should begin with the `3` largest remaining cases when at least `3` cases are available.
2. `Form 4BL` builds should begin with the `8` largest remaining cases when at least `8` cases are available.
3. Only after that startup phase should the planner continue descending one case at a time.
4. Once the first descending-order case does not fit, the planner should switch to smaller fillers.

The current code also leaves that strategy implicit enough that tests do not lock it directly.

## Goals

1. Encode printer-aware startup case seeding directly in the planner.
2. Preserve whole-case cohesion.
3. Preserve compatibility grouping by printer, resin, and layer height.
4. Keep the current XY-budget heuristic as the fit signal.
5. Reduce repeated computation by front-loading the highest-priority cases for the active printer family.
6. Keep the change local to the active `Andent_Webapp` codebase.

## Non-Goals

1. Add a live PreFormServer scene-fit probe.
2. Re-plan builds during runtime handoff.
3. Change `print_queue_service.py` fallback semantics beyond consuming the new manifests.
4. Change schemas, routers, or database shape for this feature.
5. Update `FormFlow_Dent`.

## Core Design

Build composition remains planner-owned. Runtime handoff remains execution-owned.

The planner in `app/services/build_planning.py` should own:

1. case ordering
2. startup seeding
3. descending pass
4. filler pass
5. manifest membership

The runtime handoff in `app/services/print_queue_service.py` should continue to:

1. execute the planner's manifest
2. validate the scene
3. roll back whole cases only when validation fails

The runtime layer should not duplicate case selection strategy.

## Selection Policy

### Existing Ordering Metric

"Largest" should continue to mean the current `_profile_priority(...)` ordering:

1. higher difficulty score first
2. larger total XY footprint next
3. case ID as the final stable tie-breaker

This avoids introducing a second ranking system.

### Printer-Aware Startup Window

Add a small helper in `app/services/build_planning.py` to determine startup case count:

1. `Form 4B -> 3`
2. `Form 4BL -> 8`
3. any other printer -> 1`

This helper should derive the printer from the case profile's preset catalog metadata, consistent with current compatibility grouping.

### Startup Phase

For each compatibility group:

1. Sort the remaining case profiles by `_profile_priority(...)`.
2. Seed the new build with the first case.
3. If the group has at least the printer's startup threshold remaining at build start:
   1. attempt to add the rest of that startup window in priority order
   2. add each case only if the current XY-budget heuristic says it still fits
4. If the group has fewer than the startup threshold remaining:
   1. keep the current seed-with-largest behavior
   2. do not force a partial startup window

The startup window is an attempted order, not a forced merge.

### Descending Phase

After the startup phase:

1. Continue scanning the remaining cases from largest to smallest.
2. Add each case that fits.
3. On the first case that does not fit, stop the descending phase.

The planner should not continue descending after the first fit failure.

### Filler Phase

After the descending phase stops:

1. Re-order the still-remaining cases from smallest to largest.
2. Add any case that fits.
3. Continue until no remaining smaller case fits.

This preserves the existing "use smaller fillers after large cases do not fit" behavior, but makes the transition rule explicit.

## Trigger Rules

### Form 4B

If at least `3` compatible cases remain when starting a new build:

1. attempt the top `3` cases during startup

If fewer than `3` remain:

1. use the current seed-with-largest start

### Form 4BL

If at least `8` compatible cases remain when starting a new build:

1. attempt the top `8` cases during startup

If fewer than `8` remain:

1. use the current seed-with-largest start

## Code Shape

Keep the implementation local to `app/services/build_planning.py`.

Recommended helpers:

1. `_startup_case_count(profile: CasePackProfile) -> int`
2. `_fits_with_profile(used_xy: float, candidate: CasePackProfile, xy_budget: float) -> bool`
3. one internal routine that performs:
   1. startup phase
   2. descending phase
   3. filler phase

The public entry point should remain `plan_build_manifests(rows)`.

## Runtime Interaction

No new runtime planning logic should be added to `app/services/print_queue_service.py`.

The runtime layer should continue to:

1. import files in manifest order
2. validate the scene
3. remove the last-added whole case on failure

That keeps one source of truth for build membership and ordering.

## Testing Requirements

Add tests to `tests/test_build_planning.py` first.

Required coverage:

1. `Form 4B` starts with an attempted startup window of `3` largest cases when at least `3` are available.
2. `Form 4BL` starts with an attempted startup window of `8` largest cases when at least `8` are available.
3. compatibility groups below those thresholds fall back to current seed-with-largest behavior.
4. after the first descending-order fit failure, the planner switches to smaller fillers.
5. existing case cohesion remains intact.
6. existing compatibility grouping remains intact.
7. existing non-plannable behavior remains intact.

## Acceptance Criteria

This design is complete when implementation proves:

1. build composition is still whole-case only
2. printer-aware startup windows are enforced at manifest construction time
3. descending-to-filler transition happens on first descending failure
4. `Form 4B` and `Form 4BL` behavior differ only by startup threshold, not by a separate planning algorithm
5. no runtime handoff logic is duplicated to mimic planner selection

## Risks

1. The current tests may encode behaviors that were incidental rather than intended, so some existing expectations may need to be updated.
2. Because the fit signal remains XY-budget-only, the planner can still differ from true PreForm layout outcomes on borderline scenes.
3. If printer metadata is inferred inconsistently, startup-window selection could drift from compatibility grouping. The implementation should derive both from the same preset catalog source.
