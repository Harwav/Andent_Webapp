# Form 4BL Export and XY Density Notes

This folder contains the corrected Form 4BL inspection artifacts for the `From 4BL Test Data` benchmark run.

## Corrected Scene Exports

- Source data: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`
- PreForm scene settings: `FRML-4-0`, `FLPMBE01`, `0.100 mm`, `DEFAULT`
- Exported builds: 9 local `.form` files and 9 `.png` screenshots
- Git tracking note: `.form` files are intentionally ignored because they are large generated binary artifacts. Local copies remain available in this folder after the benchmark run; the tracked evidence is the README, screenshots, and JSON summaries.
- Guardrail: each `.form` was saved only after the live scene imported the planned model count and auto-layout completed.
- Summary file: `export-summary.json`

The earlier `form_exports_existing_scenes` folder was invalid and removed. Those scenes targeted `FORM-4-0` / Form 4B and some were saved after partial imports.

## XY Density Method

The more accurate density estimate is recorded in `xy-density-mesh-projection-025mm.json`.

Platform basis:

- Form 4BL XY size from live PreFormServer material metadata: `353 mm x 196 mm`
- Platform area: `69,188 mm^2`

Calculation:

1. Query each corrected live scene by `scene_id` from `export-summary.json`.
2. For each model, load the original STL referenced by PreForm's `original_file`.
3. Transform STL vertices into scene coordinates using PreForm's reported model `position` and `orientation.z`.
4. Project transformed vertices onto XY.
5. Rasterize each model projection on a `0.25 mm` grid.
6. Apply one-cell close/fill/open per model to convert dense surface vertex samples into a filled projected footprint.
7. Union the model masks per build.
8. Compute density as:

```text
mesh_projection_density_pct =
  mesh_projection_union_area_mm2 / 69188 * 100
```

Accuracy check:

- The raster approximation was checked against direct triangle rasterization on representative models.
- The observed difference was roughly `1-4%`, which is acceptable for this packing review.
- This is more representative than bounding-box density because dental arches have large concave empty regions inside their rectangular bounds.

## Result

| Build | Models | Cases | Mesh XY density |
|---:|---:|---:|---:|
| 1 | 11 | 4 | 16.26% |
| 2 | 13 | 5 | 19.88% |
| 3 | 11 | 5 | 21.64% |
| 4 | 14 | 5 | 24.06% |
| 5 | 15 | 5 | 30.90% |
| 6 | 15 | 6 | 19.07% |
| 7 | 12 | 6 | 29.33% |
| 8 | 17 | 6 | 21.38% |
| 9 | 14 | 6 | 15.59% |

Average mesh-projection XY density: `22.01%`.

For comparison, summed XY bounding-box density averaged `50.95%`, but that overstates real occupied area because it counts empty space inside each dental arch's bounding rectangle.

## Human Pack Benchmark

The manually packed benchmark forms are in `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\Human Pack`.

Their density was calculated with the same `0.25 mm` mesh-projection method, except model placement came from `POST /load-form/` rather than the generated `export-summary.json` scene IDs. The detailed artifact is one level up at `human-pack-xy-density-mesh-projection-025mm.json`.

| Human tray | Models | Mesh XY density |
|---:|---:|---:|
| 1 | 31 | 58.58% |
| 2 | 36 | 57.95% |
| 3 | 36 | 58.75% |
| 4 | 22 | 49.24% |

Average Human Pack mesh-projection XY density: `56.13%`.

Conclusion: the generated 9-build set was substantially under-packed. The planner budget has been recalibrated to the live Form 4BL XY platform area (`69,188 mm^2`), producing 4 planned builds with model counts `[29, 34, 35, 24]`.

## Calibrated 4-Build Follow-Up

The fresh calibrated artifacts are in the sibling folder `../form4bl_form_exports_calibrated_4build/`.

That rerun saved all 4 planned Form 4BL builds as `.form` and `.png` files. It used explicit `model_spacing_mm = 0` and `allow_overlapping_supports = false`; build 2 failed with default/implicit spacing and succeeded after zero spacing was applied. The calibrated generated average mesh-projection XY density is `48.46%`.
