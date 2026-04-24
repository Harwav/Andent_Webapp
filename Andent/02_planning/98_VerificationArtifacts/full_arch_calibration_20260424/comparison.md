# Full-Arch Calibration Benchmark Comparison

## Datasets

- Calibration: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\sample_STL` was the intended calibration source named by the plan; the committed heuristic constants are covered by planner tests.
- Evaluation: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`

## Planner Comparison

| Metric | Before | After | Result |
|--------|--------|-------|--------|
| Total files | 122 | 122 | unchanged input |
| Planned builds | 11 | 4 | matches human-pack build count |
| Average cases/build | 4.36 | 12.00 | improved |
| Average models/build | 11.09 | 30.50 | close to Human Pack 31.25 |

Before planned model counts:

```text
[9, 7, 9, 10, 11, 10, 13, 15, 11, 18, 9]
```

After planned model counts:

```text
[29, 34, 35, 24]
```

Human Pack model counts:

```text
[31, 36, 36, 22]
```

Calibrated generated export counts:

```text
[29, 34, 35, 24]
```

## Human Pack XY Density Benchmark

Source forms: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\Human Pack`

Density artifact: `human-pack-xy-density-mesh-projection-025mm.json`

Method:

- Loaded each saved `.form` through `POST /load-form/` on local PreFormServer.
- Used each scene model's `original_file`, `position`, and orientation to transform the STL mesh into scene coordinates.
- Projected vertices to XY on the same `0.25 mm` raster used for the 9 generated build density artifact.
- Measured union area against the live Form 4BL platform basis: `353 mm x 196 mm = 69,188 mm^2`.

| Human tray | Models | Mesh XY density |
|---:|---:|---:|
| 1 | 31 | 58.58% |
| 2 | 36 | 57.95% |
| 3 | 36 | 58.75% |
| 4 | 22 | 49.24% |

Average Human Pack mesh-projection XY density: `56.13%`.

The previous generated 9-build exports averaged `22.01%`, so the under-packing was planner budget conservatism rather than the density calculation itself.

## Calibrated 4-Build Export Rerun

Fresh generated artifacts: `form4bl_form_exports_calibrated_4build/`

Artifacts saved:

- 4 `.form` files
- 4 `.png` screenshots
- `export-summary.json`
- `xy-density-mesh-projection-025mm.json`

Run settings:

- Source: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`
- PreForm scene: `FRML-4-0`, `FLPMBE01`, `0.100 mm`, `DEFAULT`
- Import path: `scan-to-model`, units `DETECTED`, no hollowing, no extrusion
- Layout: `models = ALL`, `mode = DENTAL`, `model_spacing_mm = 0`, `allow_overlapping_supports = false`
- Screenshot: `ZOOM_ON_MODELS`, cropped to models, `820 px`

Important rerun note: with default/implicit model spacing, build 2 failed auto-layout with `The layout tool was unable to fit all of the selected models into the work area.` Re-running that same scene with `model_spacing_mm = 0` succeeded, so the calibrated artifact run records zero spacing explicitly.

Runtime and export result:

| Metric | Result |
|--------|--------|
| Planned builds | 4 |
| Saved builds | 4 |
| Failed exports | 0 |
| Total models | 122 |
| Average models/saved build | 30.50 |
| Total PreFormServer processing time | 841.880s |
| Average processing time/build | 210.469s |

Per-build runtime:

| Build | Cases | Models | Runtime | Auto-layout | Print validation | Saved |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 11 | 29 | 212.811s | 3.352s | 116.683s | `.form` + `.png` |
| 2 | 12 | 34 | 252.268s | 14.203s | 138.770s | `.form` + `.png` |
| 3 | 14 | 35 | 225.267s | 11.193s | 122.702s | `.form` + `.png` |
| 4 | 11 | 24 | 151.531s | 2.846s | 82.488s | `.form` + `.png` |

Generated-build XY density:

| Build | Models | Mesh XY density | Mesh union area |
|---:|---:|---:|---:|
| 1 | 29 | 44.79% | 30,989.938 mm^2 |
| 2 | 34 | 61.75% | 42,724.062 mm^2 |
| 3 | 35 | 53.55% | 37,051.562 mm^2 |
| 4 | 24 | 33.74% | 23,346.750 mm^2 |

Average calibrated generated mesh-projection XY density: `48.46%`.

The generated 4-build average remains below the Human Pack average (`56.13%`), but the build count and model distribution are now comparable. Build 2 exceeds the Human Pack average density and only became auto-layoutable after explicit zero model spacing.

Planner verification:

- `tests/test_preset_catalog.py`
- `tests/test_build_planning.py`
- `tests/test_batching.py`
- `tests/test_integration.py`
- result: PASS (`61 passed`)

## Live Outcome Comparison

Before live validation reference from `before-live.md`:

- successful builds: 7
- failed builds: 4
- average models per build: 10.86
- average planner density: 0.8921
- average scene bbox density: 0.4271
- average processing time: 62.604s

Earlier after validation-only rerun from `after-live.json` before Human Pack budget calibration:

- planned builds: 9
- successful builds: 0
- failed builds: 9
- average models per successful build: 0.0
- average processing time: 30.08s

Control check:

- The same validation-only harness run with `FULL_ARCH_FACTOR = 1.0` also produced 0 successful builds and 11 failed builds.
- This means the new `after-live.json` result is not directly comparable to the earlier `before-live.md` baseline. The current validation-only run is stricter or running under different PreFormServer/import behavior than the earlier live lane.

Calibrated export rerun from `form4bl_form_exports_calibrated_4build/export-summary.json`:

- planned builds: 4
- saved builds: 4
- failed exports: 0
- total processing time: 841.880s
- average processing time/build: 210.469s
- average models/saved build: 30.50
- validation status: all 4 exported builds still report print-validation issues (`47`, `66`, `37`, `28` errors)

This rerun verifies import, auto-layout, `.form` export, screenshot export, and density capture. It does not prove final support validation is print-ready.

## Verdict

- Planner status: improved; after Human Pack calibration the planner emits 4 builds with model counts `[29, 34, 35, 24]`, comparable to the Human Pack `[31, 36, 36, 22]`.
- Export status: improved; the calibrated rerun saved all 4 generated Form 4BL `.form` files and screenshots when `model_spacing_mm = 0` was explicitly sent to PreFormServer.
- Packing-density status: improved versus the old 9-build generated set (`22.01%` average) but still below Human Pack (`48.46%` generated average vs `56.13%` Human Pack average).
- Live validation status: still a publish-readiness risk. The saved generated forms are layout/export artifacts; print validation still reports unsupported/cup issues on every build.
- Forward constraint: do not rely on implicit PreFormServer spacing for dense Form 4BL builds. The 34-model build failed with default/implicit spacing and succeeded with `model_spacing_mm = 0`.
