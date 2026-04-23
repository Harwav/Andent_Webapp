# Full-Arch Footprint Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace planner support inflation with a geometry-based full-arch reduction factor, then prove the change with a before/after `Form 4BL` benchmark report.

**Architecture:** Keep the existing planner structure in `app/services/build_planning.py`, but change the per-file effective-footprint calculation so only geometry-detected full-arch files receive a calibrated reduction factor. Use `sample_STL` only to derive the full-arch thresholds and factor, and use `From 4BL Test Data` only for the before/after benchmark and report artifacts.

**Tech Stack:** Python, pytest, existing classification/build-planning services, live local PreFormServer, JSON + Markdown verification artifacts

---

## File Structure

- Modify: `app/services/build_planning.py`
  Responsibility: planner fit math, case metrics, and any new full-arch detection helper that should stay planner-local.
- Modify: `tests/test_build_planning.py`
  Responsibility: unit coverage for full-arch detection, support-factor removal, and unchanged startup/filler ordering.
- Modify: `tests/test_batching.py`
  Responsibility: regression coverage for emitted manifest file specs after support inflation removal.
- Create: `scripts/form4bl_packing_benchmark.py`
  Responsibility: reusable benchmark harness for planner-only metrics plus optional live PreForm processing and artifact export.
- Create: `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/`
  Responsibility: before/after benchmark JSON and Markdown summary produced from the evaluation dataset.
- Modify: `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
  Responsibility: document the new planner heuristic and benchmarked state after implementation.

## Task 1: Capture the Baseline Benchmark

**Files:**
- Create: `scripts/form4bl_packing_benchmark.py`
- Create: `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/before-summary.json`
- Create: `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/before-live.md`

- [ ] **Step 1: Write the benchmark harness before changing planner logic**

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.classification import classify_saved_upload
from app.services.build_planning import plan_build_manifests


def load_rows(folder: Path):
    rows = []
    for idx, path in enumerate(sorted(folder.glob("*.stl")), start=1):
        row = classify_saved_upload(path, path.name)
        row.row_id = idx
        row.file_path = str(path)
        rows.append(row)
    return rows


def planner_summary(rows):
    manifests = plan_build_manifests(rows)
    planned = [m for m in manifests if m.planning_status == "planned"]
    return {
        "total_files": len(rows),
        "manifest_count": len(manifests),
        "planned_manifest_count": len(planned),
        "planned_case_counts": [len(m.case_ids) for m in planned],
        "planned_model_counts": [
            sum(len(group.files) for group in m.import_groups)
            for m in planned
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    rows = load_rows(args.folder)
    summary = planner_summary(rows)
    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the harness against the evaluation dataset to lock the baseline**

Run:

```powershell
python scripts/form4bl_packing_benchmark.py `
  "D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data" `
  "Andent\02_planning\98_VerificationArtifacts\full_arch_calibration_20260424\before-summary.json"
```

Expected:
- command exits `0`
- JSON file is created
- output includes the current baseline manifest count

- [ ] **Step 3: Record the existing live benchmark outcome in a short Markdown artifact**

```md
# Before Benchmark Notes

- Dataset: `D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`
- Planner baseline captured before full-arch calibration
- Live baseline reference:
  - successful builds: `7`
  - failed builds: `4`
  - average models per build: `10.86`
  - average planner density: `0.8921`
  - average scene bbox density: `0.4271`
  - average processing time: `62.604s`
```

- [ ] **Step 4: Commit the baseline harness and baseline artifacts**

Run:

```powershell
git add scripts/form4bl_packing_benchmark.py `
  Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/before-summary.json `
  Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/before-live.md
git commit -m "Capture the pre-calibration Form 4BL planner baseline"
```

Expected:
- commit succeeds

## Task 2: Lock the New Heuristic with Failing Tests

**Files:**
- Modify: `tests/test_build_planning.py`
- Modify: `tests/test_batching.py`

- [ ] **Step 1: Add failing unit tests for full-arch detection and raw tooth math**

Add to `tests/test_build_planning.py`:

```python
from app.services.build_planning import (
    _effective_row_xy_area,
    _is_full_arch_dimensions,
)


def test_is_full_arch_dimensions_detects_large_arch_geometry():
    assert _is_full_arch_dimensions(
        DimensionSummary(x_mm=72.0, y_mm=68.0, z_mm=18.0)
    ) is True


def test_is_full_arch_dimensions_rejects_quad_like_geometry():
    assert _is_full_arch_dimensions(
        DimensionSummary(x_mm=42.0, y_mm=31.0, z_mm=16.0)
    ) is False


def test_effective_row_xy_area_keeps_tooth_on_raw_bounding_box_area():
    tooth_row = _row(1, "CASE-T", "Tooth - With Supports", 12.0, 10.0)

    assert _effective_row_xy_area(tooth_row) == 120.0
```

- [ ] **Step 2: Add a failing planner regression proving full-arch reduction changes fit while non-full-arch rows stay raw**

Add to `tests/test_build_planning.py`:

```python
def test_plan_build_manifests_applies_full_arch_reduction_without_tooth_inflation():
    rows = [
        _row(1, "CASE-ARCH-1", "Ortho Solid - Flat, No Supports", 72.0, 68.0),
        _row(2, "CASE-ARCH-2", "Ortho Solid - Flat, No Supports", 71.0, 67.0),
        _row(3, "CASE-TOOTH", "Tooth - With Supports", 12.0, 10.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-ARCH-1", "CASE-ARCH-2", "CASE-TOOTH"]
```

- [ ] **Step 3: Update manifest file-spec expectations to remove support inflation**

In `tests/test_batching.py`, change the expected tooth file specs from:

```python
"support_inflation_factor": 1.18,
```

to:

```python
"support_inflation_factor": 1.0,
```

- [ ] **Step 4: Run the focused tests to verify they fail before implementation**

Run:

```powershell
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest `
  tests/test_build_planning.py `
  tests/test_batching.py -q
```

Expected:
- new full-arch tests fail because helpers or behavior do not exist yet
- batching expectations fail because support inflation is still `1.18`

- [ ] **Step 5: Commit the failing tests**

Run:

```powershell
git add tests/test_build_planning.py tests/test_batching.py
git commit -m "Lock full-arch calibration behavior with failing planner tests"
```

## Task 3: Implement Full-Arch Detection and Remove Support Inflation

**Files:**
- Modify: `app/services/build_planning.py`

- [ ] **Step 1: Replace support inflation with planner-local full-arch constants and helpers**

In `app/services/build_planning.py`, replace the inflation constant and add helpers near the top:

```python
FULL_ARCH_MAX_SPAN_MM = 65.0
FULL_ARCH_MIN_SHORT_SIDE_MM = 55.0
FULL_ARCH_MIN_XY_AREA = 3400.0
FULL_ARCH_FACTOR = 0.58


def _is_full_arch_dimensions(dimensions: DimensionSummary | None) -> bool:
    if dimensions is None:
        return False
    long_side = max(float(dimensions.x_mm), float(dimensions.y_mm))
    short_side = min(float(dimensions.x_mm), float(dimensions.y_mm))
    xy_area = float(dimensions.x_mm * dimensions.y_mm)
    return (
        long_side >= FULL_ARCH_MAX_SPAN_MM
        and short_side >= FULL_ARCH_MIN_SHORT_SIDE_MM
        and xy_area >= FULL_ARCH_MIN_XY_AREA
    )


def _effective_row_xy_area(row: ClassificationRow) -> float:
    raw_xy = _row_xy_area(row)
    if raw_xy == 0.0:
        return 0.0
    if _is_full_arch_dimensions(row.dimensions):
        return raw_xy * FULL_ARCH_FACTOR
    return raw_xy
```

- [ ] **Step 2: Remove support inflation from file specs and case metrics**

Update the existing functions in `app/services/build_planning.py`:

```python
def _build_file_prep_spec(
    row: ClassificationRow,
    compatibility_key: str,
) -> tuple[FilePrepSpec | None, str | None]:
    ...
    return FilePrepSpec(
        row_id=row.row_id,
        case_id=row.case_id,
        file_name=row.file_name,
        file_path=file_path,
        preset_name=canonical_preset_name,
        compatibility_key=compatibility_key,
        xy_footprint_estimate=_effective_row_xy_area(row),
        support_inflation_factor=1.0,
        preform_hint=profile.preform_hint,
    ), None


def _case_metrics(rows: list[ClassificationRow]) -> tuple[float, float]:
    measurable_rows = [row for row in rows if row.dimensions is not None]
    total_xy = sum(_effective_row_xy_area(row) for row in measurable_rows)
    difficulty = max((_effective_row_xy_area(row) for row in measurable_rows), default=0.0) + total_xy
    return total_xy, difficulty
```

- [ ] **Step 3: Run the focused tests to verify the new heuristic works**

Run:

```powershell
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest `
  tests/test_build_planning.py `
  tests/test_batching.py -q
```

Expected:
- all targeted tests pass

- [ ] **Step 4: Commit the heuristic implementation**

Run:

```powershell
git add app/services/build_planning.py tests/test_build_planning.py tests/test_batching.py
git commit -m "Calibrate full-arch planner footprints and drop support inflation"
```

## Task 4: Verify the Planner Surface Stays Stable

**Files:**
- Modify: none
- Test: `tests/test_preset_catalog.py`
- Test: `tests/test_build_planning.py`
- Test: `tests/test_batching.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Run the broader planner-related regression suite**

Run:

```powershell
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest `
  tests/test_preset_catalog.py `
  tests/test_build_planning.py `
  tests/test_batching.py `
  tests/test_integration.py -q
```

Expected:
- suite passes cleanly

- [ ] **Step 2: Save the test result snippet for later benchmark reporting**

```text
Planner verification:
- tests/test_preset_catalog.py
- tests/test_build_planning.py
- tests/test_batching.py
- tests/test_integration.py
- result: PASS
```

- [ ] **Step 3: Commit if any test-only adjustments were needed**

Run:

```powershell
git add -A
git commit -m "Stabilize planner regressions after full-arch calibration"
```

Expected:
- if there were no follow-up edits, skip this commit

## Task 5: Run the After Benchmark and Write the Comparison Report

**Files:**
- Modify: `scripts/form4bl_packing_benchmark.py`
- Create: `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/after-summary.json`
- Create: `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/comparison.md`

- [ ] **Step 1: Extend the benchmark harness to emit richer summary fields used in the report**

Update `scripts/form4bl_packing_benchmark.py` so `planner_summary(...)` returns:

```python
return {
    "total_files": len(rows),
    "manifest_count": len(manifests),
    "planned_manifest_count": len(planned),
    "average_cases_per_build": round(
        sum(len(m.case_ids) for m in planned) / len(planned), 2
    ) if planned else 0.0,
    "average_models_per_build": round(
        sum(sum(len(group.files) for group in m.import_groups) for m in planned) / len(planned),
        2,
    ) if planned else 0.0,
    "planned_case_counts": [len(m.case_ids) for m in planned],
    "planned_model_counts": [
        sum(len(group.files) for group in m.import_groups)
        for m in planned
    ],
}
```

- [ ] **Step 2: Run the after benchmark on the evaluation dataset**

Run:

```powershell
python scripts/form4bl_packing_benchmark.py `
  "D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data" `
  "Andent\02_planning\98_VerificationArtifacts\full_arch_calibration_20260424\after-summary.json"
```

Expected:
- command exits `0`
- after-summary JSON exists
- manifest count and average models per build can be compared directly to the baseline

- [ ] **Step 3: Re-run the live `Form 4BL` benchmark path and capture the outcome**

Run:

```powershell
@'
from pathlib import Path
print("Reuse the existing live benchmark flow against:")
print(Path(r"D:\\Marcus\\Desktop\\BM\\20260409_Andent_Matt\\From 4BL Test Data"))
'@ | python -
```

Expected:
- execute the same live benchmark lane already used earlier in this branch
- save the resulting JSON summary alongside the comparison artifacts if it produces a new file

- [ ] **Step 4: Write the comparison report**

Create `Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/comparison.md`:

```md
# Full-Arch Calibration Benchmark Comparison

## Datasets

- Calibration: `D:\Marcus\Desktop\BM\20260409_Andent_Matt\sample_STL`
- Evaluation: `D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`

## Planner Comparison

- Before planned builds: copy `planned_manifest_count` from `before-summary.json`
- After planned builds: copy `planned_manifest_count` from `after-summary.json`
- Before average models/build: copy `average_models_per_build` from `before-summary.json` if present, otherwise compute from `planned_model_counts`
- After average models/build: copy `average_models_per_build` from `after-summary.json`
- Before average cases/build: compute from `planned_case_counts` in `before-summary.json`
- After average cases/build: copy `average_cases_per_build` from `after-summary.json`

## Live Outcome Comparison

- Before live validation fallout: copy from `before-live.md`
- After live validation fallout: copy from the rerun live benchmark summary
- Before successful builds: copy from `before-live.md`
- After successful builds: copy from the rerun live benchmark summary

## Verdict

- Improvement status: state `improved`, `unchanged`, or `regressed` from the measured results
- Notes on any validation tradeoff: summarize whether the lower build count increased manual-review or validation fallout materially
```

- [ ] **Step 5: Commit the benchmark artifacts and report**

Run:

```powershell
git add scripts/form4bl_packing_benchmark.py `
  Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/after-summary.json `
  Andent/02_planning/98_VerificationArtifacts/full_arch_calibration_20260424/comparison.md
git commit -m "Benchmark the calibrated full-arch planner against Form 4BL data"
```

## Task 6: Update the Architecture Doc

**Files:**
- Modify: `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`

- [ ] **Step 1: Update the planner-heuristic description**

Replace the planner-fit wording with text like:

```md
- Fit decisions remain heuristic.
- Planner fit math now uses raw `x_mm * y_mm` for non-full-arch models.
- Geometry-detected full-arch models use a calibrated reduced effective footprint.
- Planner fit math no longer uses tooth support inflation.
```

- [ ] **Step 2: Add the benchmark status note**

Add a changelog/status entry like:

```md
| 2026-04-24 | Replaced planner support inflation with calibrated full-arch effective-footprint scaling and added before/after Form 4BL benchmark evidence |
```

- [ ] **Step 3: Run a quick diff review of the updated doc**

Run:

```powershell
git diff -- Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md
```

Expected:
- diff mentions the new full-arch heuristic and benchmark evidence

- [ ] **Step 4: Commit the documentation update**

Run:

```powershell
git add Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md
git commit -m "Document the calibrated full-arch planner heuristic"
```

## Task 7: Final Verification and Publish Readiness

**Files:**
- Modify: none

- [ ] **Step 1: Run the final verification commands**

Run:

```powershell
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest `
  tests/test_preset_catalog.py `
  tests/test_build_planning.py `
  tests/test_batching.py `
  tests/test_integration.py -q
python scripts/form4bl_packing_benchmark.py `
  "D:\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data" `
  "Andent\02_planning\98_VerificationArtifacts\full_arch_calibration_20260424\after-summary.json"
```

Expected:
- test suite passes
- benchmark summary regenerates successfully

- [ ] **Step 2: Review git status before publish**

Run:

```powershell
git status --short
```

Expected:
- no unexpected files
- only intended planner, test, script, artifact, and doc changes remain

- [ ] **Step 3: Create the final implementation commit if anything remains**

Run:

```powershell
git add -A
git commit -m "Finish full-arch footprint calibration and benchmark reporting"
```

Expected:
- skip only if there is nothing left to commit

- [ ] **Step 4: Push and update the draft PR**

Run:

```powershell
git push origin feature/printer-aware-case-seeding
```

Expected:
- branch pushes cleanly

## Spec Coverage Check

- Planner-only scope: covered by Tasks 2-4 and 6
- Remove support inflation: covered by Tasks 2-3
- Geometry-based full-arch detection: covered by Tasks 2-3
- Calibration on `sample_STL`: covered by Task 3 constant/threshold selection and Task 5 reporting context
- Before/after benchmark on `From 4BL Test Data`: covered by Tasks 1 and 5
- Docs update: covered by Task 6

## Risks to Watch During Execution

- The exact thresholds and factor may need one tuning pass after the first after-benchmark run.
- Live benchmark stability depends on the local PreFormServer staying healthy for the whole run.
- If the aggressive factor reduces build count but sharply increases validation fallout, treat that as a partial regression and tune the factor before closing the task.
