# Full-Arch Footprint Calibration Design

Date: 2026-04-24
Status: Draft for review
Scope: `Andent_Webapp` planner-only change plus before/after benchmark report

## Requirements Summary

We want to improve `Form 4BL` planner packing quality without adding live-fit probes or expensive 2D projection.

The planner should:
- keep whole-case planning intact
- keep the existing printer-aware startup seeding behavior
- stop using tooth support inflation in planner fit math
- reduce effective XY footprint only for geometry-detected full-arch models
- leave all other models on raw bounding-box XY area

Calibration source:
- `D:\Marcus\Desktop\BM\20260409_Andent_Matt\sample_STL`

Evaluation source:
- `D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`

Success priority:
1. fewer planned builds
2. more models per build
3. no major increase in live validation fallout during the `Form 4BL` benchmark run

The user explicitly prefers an aggressive heuristic. Mild planner over-admission is acceptable if live handoff later rejects some borderline cases.

## Recommended Approach

Use one calibrated, geometry-based full-arch reduction factor.

Why this approach:
- much cheaper than 2D projected silhouettes
- simpler and more explainable than a learned model
- directly addresses the main planner blind spot: full-arch bounding boxes overstate real usable footprint
- keeps the existing planner structure and tests mostly intact

Alternatives considered:
- Fixed guessed factor like `0.5x`
  Rejected because it is too arbitrary and not grounded in the calibration corpus.
- 2D projected footprint for full-arch models
  Rejected for now because a naive prototype over `sample_STL` added minutes of planner time, which is too expensive for the current workflow.
- Live scene-fit probe in the planner
  Rejected for this task because it expands scope into runtime-fit orchestration instead of improving the planner heuristic.

## Design

### 1. Effective Footprint Rule

Current planner fit math:

`effective_xy = x_mm * y_mm * support_factor`

New planner fit math:

- if model is `full_arch`:
  `effective_xy = x_mm * y_mm * full_arch_factor`
- otherwise:
  `effective_xy = x_mm * y_mm`

Notes:
- `support_factor` is removed from planner fit math entirely
- the factor applies per full-arch file, regardless of how many full-arch files are in the case
- file naming does not decide this; geometry does
- only planner fit math changes

### 2. Full-Arch Detection

Full-arch detection should be geometry-based and derived from `sample_STL`.

The detection logic should use explicit, explainable thresholds from STL bounding-box dimensions, likely including:
- max XY span threshold
- XY area threshold
- optional minimum short-side threshold to avoid classifying long narrow parts as full arches

Design intent:
- full arches should receive the reduction factor
- quads, tooth models, dies, and other smaller parts should stay at raw bounding-box XY
- antagonist files may receive the factor if their bounding box falls into the full-arch region

This means full-arch status is a derived planner property, not a model-type label.

### 3. Planner Behavior That Stays Unchanged

The following planner behavior remains unchanged:
- case grouping remains whole-case
- compatibility grouping remains printer/resin/layer-height based
- `Form 4B` startup seeding remains largest `3` when at least `3` remain
- `Form 4BL` startup seeding remains largest `8` when at least `8` remain
- descending pass still continues until the first heuristic miss
- smallest-filler fallback still starts after the first descending miss
- runtime handoff and validation flow remain unchanged

### 4. Calibration Method

Calibration uses `sample_STL` only.

Calibration steps:
1. classify and measure all STL files in `sample_STL`
2. inspect the bounding-box distribution to separate likely full arches from non-full-arch parts
3. choose explicit thresholds for the `full_arch` detector
4. derive one aggressive `full_arch_factor` from the sample corpus
5. apply that constant in planner fit math for full-arch models only

The factor should be aggressive enough to improve packing density, but still simple enough to explain and keep stable in tests.

### 5. Benchmark Method

Benchmark evaluation uses `From 4BL Test Data` only.

We should produce a before/after comparison with:
- planner manifest count
- average cases per build
- average models per build
- live processing results per build
- validation fallout count or rate
- exported `.form` and screenshot artifacts for the after run

The benchmark report should clearly separate:
- planner-only output changes
- live processing outcome changes

### 6. Acceptance Criteria

- Planner fit math no longer applies support inflation to any model.
- Planner can classify a file as `full_arch` from geometry using explicit thresholds.
- Only `full_arch` files receive the calibrated reduction factor.
- Non-full-arch files keep raw `x_mm * y_mm` planner area.
- Existing startup seeding and filler-order behavior remains intact.
- Automated tests cover full-arch detection and adjusted footprint math.
- Automated tests confirm non-full-arch models remain unchanged.
- A before/after benchmark report exists for `From 4BL Test Data`.
- The after benchmark shows fewer planned builds and/or more models per build, without a major increase in live validation fallout.

## Implementation Areas

Primary code changes:
- `app/services/build_planning.py`
- `tests/test_build_planning.py`

Possible supporting changes:
- `app/services/classification.py` if reusable geometric helpers belong there
- `app/schemas.py` only if a new planner-only field is required, though avoiding schema churn is preferred

Documentation updates after implementation:
- `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
- any benchmark artifact summary or future-design note that references planner footprint behavior

## Risks and Mitigations

Risk: Full-arch thresholds are too loose and classify quads as full arches.
Mitigation: keep detection rule explicit, inspect the sample corpus distribution, and add regression tests around borderline shapes.

Risk: The calibrated factor is too aggressive and overpacks many builds.
Mitigation: benchmark against live `Form 4BL` processing and treat validation fallout as a first-class metric.

Risk: Benchmark improvements are dataset-specific.
Mitigation: document calibration source and evaluation source separately, and keep the heuristic simple so future recalibration is straightforward.

Risk: Removing support inflation changes more than intended for tooth-heavy cases.
Mitigation: add targeted regressions proving non-full-arch tooth models now use raw XY by design, and validate against the live evaluation dataset.

## Verification Plan

Automated verification:
- run targeted planner tests for footprint math and ordering
- run the broader planner/batching test surface already used for this feature branch

Manual/live verification:
- run before benchmark on `From 4BL Test Data`
- implement calibrated full-arch heuristic
- run after benchmark on the same dataset
- compare build count, average models per build, and validation fallout

## Out of Scope

- live-fit probe planner integration
- 2D projection or silhouette packing
- runtime handoff redesign
- `FormFlow_Dent` changes
- printer dispatch behavior changes
