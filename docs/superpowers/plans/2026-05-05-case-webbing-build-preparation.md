# Plan: Case-Aware Webbing for FormFlow Build Preparation

**Status: Draft — needs review**

## Context

FormFlow prepares dental STL files for PreFormServer printing. Currently, `process_print_manifest()` sends files to PreForm and calls `auto_layout()`, which optimizes purely for packing density — same-case files get scattered across the build plate, forcing operators to sort them post-print.

The goal: group files sharing the same `case_id` by generating actual webbing geometry (thin connecting beams) between them *before* sending to PreForm, so cases stay physically connected after printing and operators don't need to manually sort.

## Open Questions (needs tuning)

1. **PreForm import with explicit positions** — does PreFormServer's `/import-model` support a position parameter? If not, need to add a new API endpoint or find an alternative
2. **Webbing STL import** — does PreFormServer's `/import-model` support naming a model (e.g., "webbing") so it can be distinguished from model files?
3. **Flat beams vs. punch-outs** — spec says flat beams (no shapely punch-out geometry), but should we revisit full tab pockets?
4. **Anti-cupping notches** — spec flags as "future" but may be needed for large builds to prevent suction distortion
5. **Packing algorithm details** — shelf-pack for case clusters is sketched but edge cases (what if a case cluster doesn't fit?) need detail

## Design Decisions (proposed)

### What replaces what
- **Replaces**: `process_print_manifest()` calling `PreFormClient.auto_layout()`
- **Bypasses**: `PreFormClient.auto_layout()` entirely — custom layout IS the layout, PreForm receives pre-positioned models
- **Keeps**: PreForm orientation, auto-support, scene validation, .form save
- **Keeps**: `plan_build_manifests()` grouping logic (unchanged)

### Layout ownership
PreForm's auto-layout is bypassed. Instead, a custom 2D packer places models grouped by case, computes XY positions, then imports models with explicit positions via `PreFormClient`. PreForm still handles orientation (Z-up reorientation) and auto-support generation.

### Webbing mode: same-case only
Beams are generated **only** between files sharing the same `case_id`. No cross-case beams. This keeps geometry simple and directly solves the sorting problem.

### Webbing geometry: flat beams, no punch-outs
Full punch-out geometry (formlabsAFA-style tab pockets with shapely buffering) is deferred. Instead, a **flat beam sheet** at `z=0` is generated: thin rectangular beams connecting closest footprint edges of same-case models. The beams are thin (2mm default) and sit flat on the build plate. PreForm's boolean merge of all meshes into one build will handle the rest.

### Dependencies
- Add `shapely` for 2D polygon buffering (beam collision detection)
- Existing `numpy`, `numpy-stl` are already used
- Existing `trimesh` is NOT needed for flat beams — `numpy-stl` can generate box primitives

## Architecture

### New module: `app/services/webbing_layout.py`

```
WebbingLayoutJob (Pydantic model)
  ├── manifest: BuildManifest
  ├── rows: list[ClassificationRow]         # STL paths + case_ids + footprint areas
  ├── output_dir: Path
  └── config: WebbingConfig

WebbingLayoutResult (Pydantic model)
  ├── status: "DONE" | "EXCEPTION"
  ├── webbing_stl_path: Path | None
  ├── model_positions: dict[str, dict]       # filename -> {x, y, z}
  └── errors: list[str]
```

### New service: `app/services/webbing_layout.py::plan_webbing_layout(job: WebbingLayoutJob) -> WebbingLayoutResult`

**Step 1 — Extract footprint centroids**
For each `ClassificationRow`, load STL via `numpy-stl`, compute projected XY centroid and convex hull boundary points at a reference Z height (e.g., z=1mm slice).

**Step 2 — Case cluster packing**
For each unique `case_id`:
- Collect all rows sharing that case_id
- Compute the convex hull of the case's combined footprint (all files in the case treated as one cluster)
- Pack case clusters into the printer XY budget using a shelf-pack variant: place clusters sequentially, largest first, on the build plate
- Within each cluster, files are placed adjacent to each other (no gap)

**Step 3 — Beam generation (Gabriel graph within each case)**
For each case cluster:
- Build Gabriel graph: edge (i,j) exists between two files if no third file's centroid falls inside the circle having segment (i,j) as diameter
- For each Gabriel edge: find closest pair of hull boundary points between the two files, create a rectangular beam (2mm wide, full tab height) connecting them
- Collision check: skip beams that cross through another case cluster's hull

**Step 4 — Generate webbing STL**
- Create 3D box mesh for each beam using `numpy-stl` or raw triangle construction
- Concatenate all beam meshes into one webbing STL
- Export to `output_dir / "webbing.stl"`

**Step 5 — Return model positions**
- Return `dict[filename, position_dict]` for all files in the manifest, where `position_dict` has `{x, y, z}` in PreForm world coordinates

### Modified: `app/services/print_queue_service.py::process_print_manifest()`

```
BEFORE:
  for each file:
      client.import_model(scene_id, stl_path, preset=preset)
  client.auto_layout(scene_id)
  client.auto_support(scene_id, models=...)
  client.save_form(...)

AFTER:
  # 1. Call new webbing layout planner
  layout_result = plan_webbing_layout(WebbingLayoutJob(manifest, rows, output_dir))
  if layout_result.status == "EXCEPTION":
      raise RuntimeError(f"Webbing layout failed: {layout_result.errors}")

  # 2. Import models with explicit positions (no auto-layout)
  for each file:
      pos = layout_result.model_positions[filename]
      client.import_model(scene_id, stl_path, preset=preset, position=pos)

  # 3. PreForm handles orientation and supports (NO auto_layout call)
  client.auto_support(scene_id, models=...)   # still runs — auto_layout is skipped

  # 4. Import webbing STL into the scene
  client.import_model(scene_id, str(layout_result.webbing_stl_path), name="webbing")

  # 5. Save
  client.save_form(...)
```

Note: PreFormClient needs a new `import_model` parameter for explicit position. If PreFormServer's `/import-model` doesn't support position, models can be imported at origin and repositioned via a scene update API — or a new endpoint is added.

### New config: `[webbing]` section in `config.toml`

```toml
[webbing]
enabled = true                    # toggle webbing on/off
thickness_mm = 2.0                # beam width
tab_height_mm = 0.8               # beam Z height (matches print layer)
max_span_mm = 50.0                # max beam length before skipping
connect_sides = true              # connect all 4 sides of each model's footprint
anti_cup_enabled = true           # add anti-cupping notches (future)
```

### Key data flow

```
Ready ClassificationRows
  |
  v
plan_build_manifests()              [build_planning.py, unchanged]
  |  groups by case_id + compatibility
  v
BuildManifest                       [schemas.py]
  |
  v
plan_webbing_layout()               [NEW: webbing_layout.py]
  |  1. Extract XY centroids + hulls from STLs
  |  2. Pack case clusters into XY budget (shelf-pack)
  |  3. Gabriel graph per case → beam list
  |  4. Write webbing.stl
  |  5. Return {filename -> (x, y, z)}
  v
model_positions: dict               [NEW]
  |
  v
process_print_manifest()           [print_queue_service.py, modified]
  |  import_model(stl, position=pos)  per file  [PreFormClient may need update]
  |  auto_support()
  |  import_model(webbing.stl)         [NEW]
  |  save_form()
  v
PrintJob with .form file
```

## Error Handling

- If webbing layout fails (e.g., STL unreadable, no valid packing), fall back to original `auto_layout()` behavior with a warning logged
- If webbing STL generation fails, fall back to auto_layout
- If PreForm import with explicit positions fails (API not supported), fall back to auto_layout

## Files to Create/Modify

**New files:**
- `app/services/webbing_layout.py` — webbing layout planner
- `tests/test_webbing_layout.py` — unit tests

**Modified files:**
- `app/services/print_queue_service.py` — call `plan_webbing_layout()` before import, add webbing STL import
- `app/services/preform_client.py` — `import_model()` may need position parameter (check PreFormServer API)
- `app/schemas.py` — add `WebbingConfig`, `WebbingLayoutJob`, `WebbingLayoutResult` Pydantic models
- `config.example.toml` — add `[webbing]` section

## Verification

1. Run existing tests to ensure no regressions in build_planning and print_queue_service
2. Send a batch of known test STL files through `plan_webbing_layout()` and verify:
   - All same-case files have beams connecting them
   - No beams cross between different cases
   - Output `webbing.stl` is a valid STL file
3. Generate a full .form file with webbing and open in PreForm to visually verify case clustering
4. Print a test build and verify operators can peel off intact case clusters
