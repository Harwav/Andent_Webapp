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

## Verdict

- Planner status: improved; after Human Pack calibration the planner emits 4 builds with model counts `[29, 34, 35, 24]`, comparable to the Human Pack `[31, 36, 36, 22]`.
- Live validation status: inconclusive for factor comparison, but the current validation-only rerun fails and should remain a publish-readiness risk.
- Tradeoff: this budget calibration intentionally uses the full live Form 4BL XY platform area as the planner gate. Final launch sign-off still needs regenerated 4-build `.form` artifacts and a comparable live benchmark lane with the same PreFormServer settings and support-generation behavior used by the before-live baseline.
