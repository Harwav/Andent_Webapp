# Calibrated Form 4BL 4-Build Export Notes

This folder contains the fresh calibrated Form 4BL inspection artifacts for `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`.

## Artifacts

- `form4bl_calibrated_build_01_11cases_29models.form`
- `form4bl_calibrated_build_01_11cases_29models.png`
- `form4bl_calibrated_build_02_12cases_34models.form`
- `form4bl_calibrated_build_02_12cases_34models.png`
- `form4bl_calibrated_build_03_14cases_35models.form`
- `form4bl_calibrated_build_03_14cases_35models.png`
- `form4bl_calibrated_build_04_11cases_24models.form`
- `form4bl_calibrated_build_04_11cases_24models.png`
- `export-summary.json`
- `xy-density-mesh-projection-025mm.json`

## Run Settings

- PreFormServer URL: `http://127.0.0.1:44388`
- Scene: `FRML-4-0`, `FLPMBE01`, `0.100 mm`, `DEFAULT`
- Import: `scan-to-model`, units `DETECTED`, no hollowing, no extrusion
- Layout: `models = ALL`, `mode = DENTAL`, `model_spacing_mm = 0`, `allow_overlapping_supports = false`
- Screenshot: `ZOOM_ON_MODELS`, cropped to models, `820 px`

Important: build 2 failed auto-layout with default/implicit model spacing. Re-running the same 34-model scene with `model_spacing_mm = 0` succeeded, so zero spacing is part of the calibrated benchmark condition.

## Runtime

| Build | Cases | Models | Total runtime | Auto-layout | Print validation |
|---:|---:|---:|---:|---:|---:|
| 1 | 11 | 29 | 212.811s | 3.352s | 116.683s |
| 2 | 12 | 34 | 252.268s | 14.203s | 138.770s |
| 3 | 14 | 35 | 225.267s | 11.193s | 122.702s |
| 4 | 11 | 24 | 151.531s | 2.846s | 82.488s |

Summary:

- Planned builds: `4`
- Saved builds: `4`
- Failed exports: `0`
- Total models: `122`
- Average models/saved build: `30.50`
- Total PreFormServer processing time: `841.880s`
- Average processing time/build: `210.469s`

## XY Density

Method: transformed STL vertex projection on a `0.25 mm` raster with one-cell close/fill/open per model, measured against the full Form 4BL XY platform (`353 mm x 196 mm = 69,188 mm^2`).

| Build | Models | Mesh XY density | Mesh union area |
|---:|---:|---:|---:|
| 1 | 29 | 44.79% | 30,989.938 mm^2 |
| 2 | 34 | 61.75% | 42,724.062 mm^2 |
| 3 | 35 | 53.55% | 37,051.562 mm^2 |
| 4 | 24 | 33.74% | 23,346.750 mm^2 |

Average mesh-projection XY density: `48.46%`.

For comparison:

- Earlier generated 9-build average: `22.01%`
- Human Pack average: `56.13%`

## Validation Note

All 4 generated builds exported successfully, but print validation still reports support/cup issues:

- Build 1: `47` validation errors
- Build 2: `66` validation errors
- Build 3: `37` validation errors
- Build 4: `28` validation errors

These artifacts prove import, auto-layout, packing density, `.form` export, and screenshot export. They do not prove final print-ready support validation.
