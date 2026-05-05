# formlabsAFA Developer Reference

## Architecture

```
formlabsAFA/
  __main__.py          CLI entry point, startup/shutdown, signal handling
  config.py            Pydantic config models, TOML loader
  context.py           AppContext (shared state), WorkspacePaths
  batch.py             BatchOrchestrator — full pipeline per batch
  layout.py            Auto-layout with fallback: SWAP → GRID → remove smallest
  queue.py             ModelQueue — sorted deque of pending STL filenames
  watcher.py           Filesystem watchers (watchdog) + queue processing loop
  db.py                SQLite model status tracking
  log.py               Rich console + file logging, tprint() timestamps
  frame_profile.py     Frame STL loading, spanner derivation, profile selection
  api.py               Optional FastAPI REST endpoints
  mesh/
    chamfer.py         Chamfer locating features, body merge (boolean union)
    geometry.py        2D geometry helpers, Box2D, grid placement
    punch.py           Boolean subtraction of model footprints from frame
    webbing.py         Dynamic web generation between models (Gabriel graph)
  preform/
    client.py          Async HTTP client for PreForm Server (all endpoints)
    operations.py      Long-running operation polling
    server.py          PreForm Server process start/stop/connect
```

## Pipeline (batch.py:_process_batch)

1. **Merge** — Boolean-union multi-body STLs so label letters survive scan-to-model. Runs in parallel threads. (`mesh/chamfer.py:merge_bodies`)
2. **Chamfer** — Optional. Slices locating features to prevent flashing. (`mesh/chamfer.py`)
3. **Import** — `scan-to-model` endpoint: hollows, adds drain holes, imports into PreForm scene. Models with cups get reimported without hollowing.
4. **Orient** — All models set to z-up via `update_model`. Sequential (PreForm requirement).
5. **Layout** — Frame mode: `auto-layout` with fallback strategies. Webbing mode: free `auto-layout` with rotation unlocked.
6. **Frame or Webbing** — see below
7. **Fixtures** — Optional. Imports `modelFixture.stl` at each model's position + orientation.
8. **Save** — Exports `.form` file to `workspace/3-batches-to-print/`.

## Frame Mode vs Webbing Mode

| | Frame Mode | Webbing Mode |
|---|---|---|
| Config | `webbing.enabled = false` | `webbing.enabled = true` |
| Structure | Pre-made STL from `frame_profiles/` | Generated dynamically |
| Layout | Constrained to spanners | Free packing, rotation unlocked |
| Selection | Auto-selects small/large by model count | N/A |
| Punch | Convex hull at tab height, eroded inset | Same, applied to web sheet |
| Best for | Standardized production | Max packing density |

## Fixturing

- `modelFixture.stl` in `frame_profiles/` — generic locating feature that hollowing removes (replace with your own)
- Inserted as a separate part at each model's exact position + orientation
- Config: `[fixture] enabled = true, stl_path = "frame_profiles/modelFixture.stl"`
- Orientation matching: when models are rotated during layout, fixtures rotate to match

## Hollowing & Drain Holes

All handled by PreForm's `scan-to-model` endpoint in one call:
- `[hollowing] enabled, shell_thickness_mm, honeycomb_infill`
- `[drain_holes] radius_mm, height_ratio, suppression_distance_mm, max_count`
- Hardcoded in batch.py: `cutoff_height_mm=0.01`, `extrude_distance_mm=0.11`

## Webbing Details

- **Neighbor finding**: Gabriel graph on model centroids — edge exists only if no other model centroid falls inside the circle with that edge as diameter
- **Beam routing**: Closest convex hull points between each neighbor pair
- **Collision filter**: Beams that cross through another model's footprint are rejected
- **Perimeter rail**: Convex hull of all footprint points, beams between consecutive hull vertices (skip segments < 10mm)
- **Anti-cupping**: Half-circle arches cut from build plate upward on beams > `anti_cup_min_span_mm`
- **Punch**: Convex hull footprint with `punch_offset_mm` buffer, same tab + breakaway as frame mode

## Logging

| File | Content |
|---|---|
| `workspace/logs/formlabsAFA.log` | Global log, always DEBUG level |
| `workspace/logs/batch-{N}.log` | Per-batch audit trail: inputs, steps, output, timing |
| Console | INFO by default, DEBUG with `debug = true` |

Batch logs use ISO 8601 timestamps for traceability.

## Config Reference

| Section | Key settings |
|---|---|
| `[general]` | `base_path`, `debug` |
| `[printer]` | `serial_or_group_queue_id`, `upload_to_printer` |
| `[preform_server]` | `host`, `port` |
| `[material]` | `machine_type`, `material_code`, `print_setting` |
| `[batch]` | `initial_batch_size`, `n_parallel_batches`, `process_partial_batches` |
| `[hollowing]` | `enabled`, `shell_thickness_mm`, `honeycomb_infill` |
| `[drain_holes]` | `radius_mm`, `height_ratio`, `max_count` |
| `[chamfer]` | `enabled`, `leg_depth_mm`, `height_mm` |
| `[layout]` | `model_spacing_mm`, `front/back_clearance_mm`, `bounds` |
| `[frame_tabs]` | `height_mm`, `connection_distance_mm` |
| `[breakaway]` | `enabled`, `width_mm`, `height_mm` |
| `[frame]` | `profiles_dir`, `large_frame_cutoff` |
| `[webbing]` | `enabled`, `thickness_mm`, `height_mm`, `punch_offset_mm`, `anti_cup_*`, `connect_front/back/left/right` |
| `[fixture]` | `enabled`, `stl_path` |
| `[support]` | `support_all_minima` |

## Known Limitations

- **Label merge**: Some STL files have label bodies that fail boolean union (non-watertight geometry). These labels are lost. Logged at INFO level.
- **Layout time**: The SWAP → GRID → remove cascade can take 30-120s per batch. Capped at 50 iterations.
- **21+ models**: PreForm's auto-layout may fail to pack more than ~20 dental arches on a Form 4 platform.
- **Webbing geometry**: Convex hull footprint, not true contour. The U-cavity is covered but the web extends slightly beyond the actual arch outline.
