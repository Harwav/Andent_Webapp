# Full-Arch Calibration Benchmark Comparison

## Datasets

- Calibration: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\sample_STL` was the intended calibration source named by the plan; the committed heuristic constants are covered by planner tests.
- Evaluation: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`

## Planner Comparison

| Metric | Before | After | Result |
|--------|--------|-------|--------|
| Total files | 122 | 122 | unchanged input |
| Planned builds | 11 | 9 | improved |
| Average cases/build | 4.36 | 5.33 | improved |
| Average models/build | 11.09 | 13.56 | improved |

Before planned model counts:

```text
[9, 7, 9, 10, 11, 10, 13, 15, 11, 18, 9]
```

After planned model counts:

```text
[11, 13, 11, 14, 15, 15, 12, 17, 14]
```

Planner verification:

- `tests/test_preset_catalog.py`
- `tests/test_build_planning.py`
- `tests/test_batching.py`
- `tests/test_integration.py`
- result: PASS (`60 passed`)

## Live Outcome Comparison

Before live validation reference from `before-live.md`:

- successful builds: 7
- failed builds: 4
- average models per build: 10.86
- average planner density: 0.8921
- average scene bbox density: 0.4271
- average processing time: 62.604s

After validation-only rerun from `after-live.json`:

- planned builds: 9
- successful builds: 0
- failed builds: 9
- average models per successful build: 0.0
- average processing time: 30.08s

Control check:

- The same validation-only harness run with `FULL_ARCH_FACTOR = 1.0` also produced 0 successful builds and 11 failed builds.
- This means the new `after-live.json` result is not directly comparable to the earlier `before-live.md` baseline. The current validation-only run is stricter or running under different PreFormServer/import behavior than the earlier live lane.

## Verdict

- Planner status: improved.
- Live validation status: inconclusive for factor comparison, but the current validation-only rerun fails and should remain a publish-readiness risk.
- Tradeoff: the calibrated planner reduces build count from 11 to 9 and increases average models/build from 11.09 to 13.56, but final launch sign-off still needs a comparable live benchmark lane with the same PreFormServer settings and support-generation behavior used by the before-live baseline.
