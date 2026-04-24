# Form 4BL Export and XY Density Notes

This folder contains the corrected Form 4BL inspection artifacts for the `From 4BL Test Data` benchmark run.

## Corrected Scene Exports

- Source data: `C:\Users\Marcus\Desktop\BM\20260409_Andent_Matt\From 4BL Test Data`
- PreForm scene settings: `FRML-4-0`, `FLPMBE01`, `0.100 mm`, `DEFAULT`
- Exported builds: 9 `.form` files and 9 `.png` screenshots
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
