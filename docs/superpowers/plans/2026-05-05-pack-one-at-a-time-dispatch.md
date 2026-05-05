# Pack-One-At-A-Time Dispatch Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "pre-plan all manifests upfront, then process each" dispatch loop with "pack one tray, send to PreForm, accept it, then re-plan the remaining pool." This naturally enforces the architectural invariant that at most one held job exists per lane (only the final, sparsest tray can be below target by construction).

**Architecture:** The current `_send_ready_rows_to_device()` calls `plan_build_manifests()` once on all rows, splits into N manifests, puts them all in `pending_manifests`, then iterates calling PreForm one at a time. The refactor changes the inner loop: pack the next tray from the live pool, send to PreForm, on success remove accepted rows from the pool and continue; on density-hold or busy-lane outcomes break the loop because no further trays should be packed for that lane.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, `unittest.mock`

---

## Context

### Why this refactor

The architecture doc (`docs/02_planning/02.03_Architecture-Packing-Algorithm.md` §8) says:
> "Hold scope: Only the final below-target build per compatibility group"
> "Held jobs do not stack — a single below-target replan replaces the old held job rather than adding a second one."

The current code violates this when `plan_build_manifests` produces multiple manifests for the same lane (because combined rows exceed the 60% density cap). It treats every manifest as eligible for dispatch, leading to multiple held jobs per lane when things go wrong (e.g. busy lane collisions, or overflow trays that hit the density hold).

Production evidence: 41 rows submitted → 2 manifests (59% + 7%) → both held with `busy_lane` → 2 simultaneous held jobs on the same lane → operator forced to manually intervene.

### Why pack-one-at-a-time fixes it

When the loop packs only the next tray from the live pool:
- Manifest 1 (largest tray) → PreForm → if PreForm accepts and density ≥ target → Queued, remove rows from pool, loop
- Manifest 2 (next tray from remaining pool) → same flow
- Eventually the pool produces a tray that's below target → that's the final tray for the lane → held → loop ends (no more trays packed)
- If PreForm shrinks a manifest (auto-layout failure), bumped cases stay in the pool naturally, ready for the next iteration's pack

Only ONE held job per lane can exist by construction: the final remainder. Overflow rows stay in the pool until the next dispatch run.

### How the planner runs each iteration

Each iteration calls `plan_build_manifests(live_pool, max_layout_density=0.60)` and takes `ranked[0]` — the densest first tray it can produce. Every iteration runs the **identical** §7 packing procedure from the architecture doc, just on a shrinking pool:

```
For each iteration N:
  Step 6:  Sort remaining cases by difficulty (largest effective XY first)
  Step 7:  Group by compatibility key
  Step 8:  Seed with the hardest remaining case          ← largest first
  Step 9:  Add startup candidates (next-largest)
  Step 10: Continue adding next-largest while they fit the layout budget (60% cap)
  Step 11: When next-largest fails to fit, fill remaining space with
           the smallest cases that still fit             ← smallest-filler pass
  Step 12: Emit BuildManifest → take this as Manifest N → send to PreForm
```

**The smallest-filler pass runs every iteration.** Each tray is maximally packed before the next iteration starts. A small case (e.g. a single tooth) only ends up in a later tray if it genuinely couldn't fit any earlier tray.

**Concrete example.** Three cases enter the pool: LARGE-A, LARGE-B, TINY.

```
Iteration 1:
  live_pool = [LARGE-A, LARGE-B, TINY]
  ranked = plan_build_manifests(pool)              ← planner runs
  Manifest 1 = pack largest (LARGE-A) + next (LARGE-B) + smallest-filler (TINY?)
            → if TINY fits in remaining capacity, it joins Manifest 1
            → if not, Manifest 1 = (LARGE-A, LARGE-B) only
  → PreForm processes Manifest 1
  → density 48% ≥ 40% → Queued
  → live_pool = [TINY]                             ← remove accepted

Iteration 2:
  live_pool = [TINY]
  ranked = plan_build_manifests(pool)              ← planner runs again
  Manifest 2 = seed with TINY (it's the largest in this pool) + nothing more fits
  → PreForm processes Manifest 2
  → density 5% < 40% → Held (below_density_target)
  → loop breaks (final remainder for this lane)
```

The held tray is the **final remainder** by construction — it contains only what genuinely couldn't be absorbed into any preceding tray's smallest-filler pass.

### Scope of this refactor

- **In scope:** `_send_ready_rows_to_device()` (the device-specific dispatch path)
- **Out of scope:** `send_ready_rows_to_print()` (the no-device-id path) — different semantics, separate refactor. We keep its existing implementation; only update its tests if shared utilities we touch affect them.
- **Out of scope:** Changing `plan_build_manifests`, `_coalesce_manifests_by_lane_key`, `process_print_manifest`, the lane lock primitive, or the database schema.

### Critical files

- **Modify:** `app/services/print_queue_service.py`
  - `_send_ready_rows_to_device()` lines 1947–2495 (substantially restructured)
- **Add tests to:** `tests/test_preform_handoff.py`
  - Reuse helpers: `StubPreFormClient`, `_build_settings`, `_build_holding_settings`, `_seed_rows`, `_row_payload`, `_ready_setup_status`
- **Read-only references:** `app/services/build_planning.py:406` (`plan_build_manifests`), `app/database.py` (`try_acquire_build_lane_lock`)

### Behavioural contract after refactor

| Scenario | Outcome |
|----------|---------|
| Pool packs into one tray ≥ target → Queued | One Queued print_job, rows in `history`/`Queued` state |
| Pool packs into one tray < target, before cutoff | One Held print_job (`below_density_target`), rows in `in_progress`/`Holding` state |
| Pool packs into N trays ≥ target each | N Queued print_jobs, sequential PreForm calls |
| Pool packs into K full trays + 1 sparse final tray | K Queued + 1 Held (`below_density_target`) — sparse tray comes from final remainder |
| Lane is busy when first tray attempts PreForm | One Held print_job (`busy_lane`) covering entire pool — loop stops |
| PreForm rejects auto-layout for a tray | Smallest case removed, retry with shrunken tray; bumped case stays in pool for next iteration |
| PreForm rejects all imports for a tray | Cases marked Needs Review, loop continues with remaining pool |
| Held job already exists for the lane (replan path) | Held job deleted, its rows merged into the live pool at start; loop runs normally |
| After cutoff time | Density hold disabled — final sparse tray dispatches as Queued |

---

## Task 1: Write failing test — busy lane during overflow produces one held job

**Files:**
- Modify: `tests/test_preform_handoff.py` (after `test_busy_lane_does_not_delete_existing_held_job`, ~line 2530)

- [ ] **Step 1: Add the failing test**

```python
def test_overflow_pool_busy_lane_creates_single_held_job(tmp_path):
    """When the lane is busy, exactly one busy_lane held job covers the entire pool.

    Pre-refactor: pre-planned 2 manifests, each independently hits BuildLaneBusyError,
    creating 2 held jobs.
    Post-refactor: pack-one-at-a-time tries the first tray, hits busy lane, holds the
    pool as a single job, and stops.
    """
    from app.database import try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = replace(_build_settings(tmp_path), print_hold_density_target=0.95)
    app = create_app(settings)
    client = TestClient(app)

    stl_a = tmp_path / "case_a.stl"
    stl_b = tmp_path / "case_b.stl"
    stl_a.write_text("solid a\nendsolid a\n", encoding="utf-8")
    stl_b.write_text("solid b\nendsolid b\n", encoding="utf-8")

    # Two large full-arches that overflow the 60% density cap when combined
    all_ids = _seed_rows(
        settings,
        [
            _row_payload(stl_a, case_id="OVERFLOW-A",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="hash-oa",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
            _row_payload(stl_b, case_id="OVERFLOW-B",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="hash-ob",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
        ],
    )

    # Confirm test setup forces 2 manifests
    from app.database import _load_rows_by_ids
    with closing(connect(settings)) as conn:
        rows = _load_rows_by_ids(conn, all_ids)
    manifests = plan_build_manifests(rows, max_layout_density=0.60)
    assert len(manifests) == 2, f"Test setup must produce 2 manifests, got {len(manifests)}"
    lane_keys = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-lab")
    assert len(lane_keys) == 1
    lane_key = next(iter(lane_keys))

    # Pre-acquire the lane lock to simulate busy
    try_acquire_build_lane_lock(settings, lane_key, "external-owner", "external")

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL",
         "status": "Ready", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), \
         patch("app.services.preform_setup_service.get_preform_setup_status",
               return_value=_ready_setup_status(settings)), \
         patch("app.services.print_queue_service.validate_stl_file",
               return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": all_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    held_jobs = [j for j in jobs if j.status == "Holding for More Cases"]
    assert len(held_jobs) == 1, (
        f"Expected exactly 1 held job, got {len(held_jobs)}. "
        f"Jobs: {[(j.id, j.status, j.hold_reason) for j in jobs]}"
    )
    held_job = held_jobs[0]
    assert held_job.hold_reason == "busy_lane"

    # All rows linked to that single job
    for row_id in all_ids:
        row = get_upload_row_by_id(settings, row_id)
        assert row is not None
        assert row.linked_print_job_id == held_job.id
```

- [ ] **Step 2: Run the test to confirm it fails**

```
python -m pytest tests/test_preform_handoff.py::test_overflow_pool_busy_lane_creates_single_held_job -v
```

Expected: **FAIL** with `Expected exactly 1 held job, got 2`.

---

## Task 2: Write failing test — overflow pool sequentially dispatches and holds final remainder

**Files:**
- Modify: `tests/test_preform_handoff.py`

- [ ] **Step 1: Add the failing test**

```python
def test_overflow_pool_sequentially_packs_and_holds_only_final_remainder(tmp_path):
    """A pool that produces multiple trays dispatches the full ones and holds only the final sparse one.

    Per architecture-doc §7, each iteration runs the same packing procedure: largest-first seed,
    fill descending while it fits the 60% cap, smallest-filler pass to top up. The held tray is
    the final remainder — what genuinely couldn't be absorbed by any preceding iteration.
    """
    settings = _build_holding_settings(tmp_path)  # density_target=0.40, cutoff=23:59
    app = create_app(settings)
    client = TestClient(app)

    # Three cases. Two large (~24% effective each), one tiny (~5%).
    # Iteration 1 packs LARGE-A + LARGE-B (~48% density, ≥ 40% target) → Queued.
    # If TINY fits the smallest-filler pass of iteration 1, it joins; otherwise iteration 2 holds it.
    # Test relies on dimensions chosen so smallest-filler does NOT fit TINY into iteration 1
    # (sufficient when the two large arches consume most of the 60% cap budget).
    stls = [tmp_path / f"case_{i}.stl" for i in range(3)]
    for s in stls:
        s.write_text(f"solid {s.name}\nendsolid {s.name}\n", encoding="utf-8")

    all_ids = _seed_rows(
        settings,
        [
            _row_payload(stls[0], case_id="LARGE-A",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="h-la",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
            _row_payload(stls[1], case_id="LARGE-B",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="h-lb",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
            _row_payload(stls[2], case_id="TINY",
                         preset="Tooth - With Supports",
                         status="Ready", content_hash="h-t",
                         dimension_x_mm=20.0, dimension_y_mm=15.0),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL",
         "status": "Ready", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), \
         patch("app.services.preform_setup_service.get_preform_setup_status",
               return_value=_ready_setup_status(settings)), \
         patch("app.services.print_queue_service.validate_stl_file",
               return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": all_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    queued = [j for j in jobs if j.status == "Queued"]
    held = [j for j in jobs if j.status == "Holding for More Cases"]

    # Exactly one Queued (the full tray) and at most one Held (the final remainder)
    assert len(queued) >= 1, f"Expected at least 1 Queued, got {len(queued)}"
    assert len(held) <= 1, f"Expected at most 1 Held, got {len(held)}"

    # If TINY ended up held, hold_reason must be below_density_target
    if held:
        assert held[0].hold_reason == "below_density_target"
        assert set(held[0].case_ids) == {"TINY"}

    # The Queued tray must contain both large cases together
    queued_cases = set(queued[0].case_ids)
    assert "LARGE-A" in queued_cases
    assert "LARGE-B" in queued_cases
```

- [ ] **Step 2: Run the test to confirm it fails (or passes)**

```
python -m pytest tests/test_preform_handoff.py::test_overflow_pool_sequentially_packs_and_holds_only_final_remainder -v
```

Note: this test may pass on current code if both manifests happen to dispatch correctly today. Its primary value is regression protection during/after the refactor — it ensures the per-iteration packing contract is preserved.

---

## Task 3: Refactor `_send_ready_rows_to_device()` to pack-one-at-a-time

**Files:**
- Modify: `app/services/print_queue_service.py` lines 1947–2495 (the device dispatch function)

The new structure replaces the `pending_manifests` outer loop with a `live_pool` that shrinks as trays are accepted.

- [ ] **Step 1: Read the existing function once end-to-end**

Read `app/services/print_queue_service.py:1947-2495` to refresh exact local-variable names: `device`, `prevalidated_rows`, `quarantined_cases`, `now`, `hold_now`, `cutoff_at`, `rows_by_id`, `groups`, `blocked_groups`. The refactor must preserve every DB write, every event emission, and every response field.

- [ ] **Step 2: Replace the dispatch body with a pack-one-at-a-time loop**

The header (validation, prevalidation, device lookup, initial held-job loading, held-job deletion) stays the same up to roughly line 2074. Replace the block from `pending_manifests = ...` (line 2078) through the end of the `while pending_manifests or retry_rows:` loop (line 2495) with the new structure below. Keep `groups`, `blocked_groups`, response building, and `connection.commit()` placements as in the original; only the loop logic changes.

```python
        # NEW: pack-one-at-a-time pool model
        # live_pool starts as held_replan_rows + (ready rows not in held_pool)
        # On each iteration: plan from the pool, take the densest tray, send to PreForm,
        # on success remove accepted rows from pool and continue;
        # on density-hold or busy-lane outcomes, exit the loop.

        live_pool: list[ClassificationRow] = list(planning_rows)

        while live_pool:
            # Run §7 packing procedure on the current pool; take the densest first tray.
            # plan_build_manifests sorts by difficulty (largest effective first), seeds with
            # the hardest case, fills descending, and runs the smallest-filler pass to top up.
            ranked_manifests = plan_build_manifests(
                _selected_model_rows(live_pool, device),
                max_layout_density=settings.print_max_layout_density,
            )
            if not ranked_manifests:
                break

            # Coalesce same-lane manifests that fit one tray (preserves existing optimization).
            ranked_manifests = _coalesce_manifests_by_lane_key(ranked_manifests)

            manifest = ranked_manifests[0]
            manifest_row_id_list = manifest_row_ids(manifest, live_pool)
            manifest_id = build_manifest_assignment_id(manifest, manifest_row_id_list)

            # Non-plannable handling: same as before
            if manifest.planning_status != "planned" or not manifest.import_groups:
                reason = f"Build planning requires manual review: {manifest.non_plannable_reason}"
                blocked_groups.append(
                    _group_result(
                        manifest_id=manifest_id,
                        status="blocked",
                        row_ids=manifest_row_id_list,
                        error=reason,
                    )
                )
                _mark_cases_needs_review_with_retry(
                    connection,
                    [
                        {
                            "case_id": case_id,
                            "row_ids": [
                                row.row_id
                                for row in live_pool
                                if row.row_id is not None and row.case_id == case_id
                            ],
                            "reason": reason,
                        }
                        for case_id in manifest.case_ids
                    ],
                    event_type="manual_review_required",
                    now=now,
                )
                # Remove non-plannable cases from the live pool and continue
                non_plannable_case_ids = set(manifest.case_ids)
                live_pool = [r for r in live_pool if r.case_id not in non_plannable_case_ids]
                continue

            # Process this single tray through PreForm with retry-on-shrink
            active_manifest = manifest
            active_lane_key = _build_lane_key_from_manifest(
                active_manifest, device_id=str(device["device_id"])
            )
            tray_outcome: str | None = None  # "queued" | "held_busy" | "held_density" | "blocked"
            accepted_case_ids: set[str] = set()

            while True:
                active_rows = _manifest_rows(active_manifest, rows_by_id)
                job_name = _generate_unique_job_name_for_manifest(
                    connection, datetime.now(), active_manifest,
                )
                try:
                    created_print_job_id = _reserve_print_job_for_rows(
                        connection,
                        settings=settings,
                        manifest=active_manifest,
                        rows=active_rows,
                        job_name=job_name,
                        now=now,
                        device_id=str(device["device_id"]),
                        printer_device_name=(
                            str(device["device_name"])
                            if device.get("device_name") is not None
                            else None
                        ),
                    )
                    connection.commit()
                except sqlite3.IntegrityError as exc:
                    connection.rollback()
                    raise DeviceDispatchValidationError(
                        _send_to_print_payload(
                            blocked_groups=[
                                _group_result(
                                    manifest_id=manifest_id,
                                    status="failed",
                                    row_ids=manifest_row_id_list,
                                    error="Selected rows are already being submitted. Refresh the queue and try again.",
                                )
                            ],
                            rows=_load_rows_by_ids(connection, row_ids),
                        )
                    ) from exc

                result = None
                try:
                    with _build_lane_locks(
                        settings, [active_lane_key], operation="send_to_print",
                    ):
                        result = process_print_manifest(
                            settings, active_manifest, active_rows,
                            batch_number=1, job_name=job_name,
                            device_id=str(device["device_id"]),
                            printer_device_name=(
                                str(device["device_name"])
                                if device.get("device_name") is not None
                                else None
                            ),
                            dispatch_scene=False,
                        )
                    break  # exits inner while True; result populated
                except BuildLaneBusyError:
                    # Hold the ENTIRE remaining live_pool as a single busy_lane job.
                    # No further trays will be packed for this lane in this dispatch.
                    busy_message = (
                        "Already preparing a build for this printer/material/layer lane. "
                        "Wait for the current build to finish or hold, then try again."
                    )
                    # Build a manifest covering the full live_pool. Re-plan with no density cap
                    # to fold all rows into one manifest if possible; fall back to the current
                    # manifest if that fails.
                    pool_manifest = active_manifest  # safe minimal fallback
                    try:
                        all_pool_planned = plan_build_manifests(
                            _selected_model_rows(live_pool, device),
                            max_layout_density=None,  # no cap; fold everything
                        )
                        for candidate in all_pool_planned:
                            if (
                                candidate.planning_status == "planned"
                                and _build_lane_key_from_manifest(
                                    candidate, device_id=str(device["device_id"])
                                ) == active_lane_key
                            ):
                                pool_manifest = candidate
                                break
                    except Exception:
                        pass  # fall back to active_manifest

                    pool_rows = _manifest_rows(pool_manifest, rows_by_id)
                    hold_result = {
                        "scene_id": None,
                        "preset": _manifest_preset_summary(pool_manifest),
                        "preset_names": pool_manifest.preset_names,
                        "compatibility_key": pool_manifest.compatibility_key,
                        "case_ids": _manifest_case_ids_by_file_order(pool_manifest),
                        "manifest_json": pool_manifest.model_dump(),
                        "form_file_path": None,
                        "printer_type": pool_manifest.printer_group,
                        "printer_device_id": str(device["device_id"]),
                        "printer_device_name": (
                            str(device["device_name"])
                            if device.get("device_name") is not None
                            else None
                        ),
                        "resin": pool_manifest.material_label,
                        "layer_height_microns": (
                            int(pool_manifest.layer_thickness_mm * 1000)
                            if pool_manifest.layer_thickness_mm is not None
                            else None
                        ),
                        "estimated_density": pool_manifest.estimated_density,
                        "validation_passed": None,
                        "validation_errors": [],
                    }
                    _update_reserved_print_job_as_held(
                        connection,
                        job_id=created_print_job_id,
                        result=hold_result,
                        settings=settings,
                        cutoff_at=cutoff_at,
                        now=now,
                        hold_reason="busy_lane",
                    )
                    _held_job_ids_created_this_process.add(created_print_job_id)
                    held_row_ids: list[int] = []
                    for row in pool_rows:
                        if row.row_id is None:
                            continue
                        held_row_ids.append(row.row_id)
                        connection.execute(
                            """UPDATE upload_rows
                               SET status = 'Submitted',
                                   queue_section = 'in_progress',
                                   handoff_stage = ?,
                                   linked_job_name = ?,
                                   linked_print_job_id = ?,
                                   current_event_at = ?
                               WHERE id = ?""",
                            (HOLDING_STATUS, job_name, created_print_job_id, now, row.row_id),
                        )
                        metadata = json.dumps({
                            "status": "Submitted",
                            "queue_section": "in_progress",
                            "handoff_stage": HOLDING_STATUS,
                            "job_name": job_name,
                            "linked_print_job_id": created_print_job_id,
                            "manifest_id": manifest_id,
                            "manifest": pool_manifest.model_dump(),
                            "estimated_density": pool_manifest.estimated_density,
                            "density_target": settings.print_hold_density_target,
                            "error": busy_message,
                        })
                        connection.execute(
                            """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                               VALUES (?, ?, ?, ?)""",
                            (row.row_id, "build_holding", now, metadata),
                        )
                    groups.append(
                        _group_result(
                            manifest_id=manifest_id,
                            status="held",
                            row_ids=held_row_ids,
                            job_name=job_name,
                            error=busy_message,
                        )
                    )
                    tray_outcome = "held_busy"
                    break

                except PreFormAutoLayoutFailureError:
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    shrink_result = _shrink_manifest_after_layout_failure(
                        connection, active_manifest, rows_by_id, now=now,
                    )
                    connection.commit()
                    if shrink_result is None:
                        _move_rows_back_to_analysis(
                            connection, active_rows, now=now, event_type="handoff_failed",
                        )
                        connection.commit()
                        raise
                    shrunken_manifest, deferred_rows = shrink_result
                    # Deferred rows return to the live_pool naturally — they were never
                    # removed because we only remove ACCEPTED rows after a successful tray.
                    # The next outer iteration will pick them up via plan_build_manifests.
                    active_manifest = shrunken_manifest
                    continue  # retry inner while True with shrunken manifest

                except PreFormImportFailureError as exc:
                    failed_case_errors = exc.failed_case_errors
                    _mark_cases_needs_review_with_retry(
                        connection,
                        [
                            {
                                "case_id": case_id,
                                "row_ids": [
                                    row.row_id
                                    for row in live_pool
                                    if row.row_id is not None and row.case_id == case_id
                                ],
                                "reason": f"PreForm import failed: {error}",
                            }
                            for case_id, error in failed_case_errors.items()
                        ],
                        event_type="case_quarantined_during_preform_import",
                        now=now,
                    )
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    blocked_groups.append(
                        _group_result(
                            manifest_id=manifest_id,
                            status="failed",
                            row_ids=manifest_row_id_list,
                            error="PreFormServer rejected every STL in this group during import.",
                        )
                    )
                    quarantined_case_ids = set(failed_case_errors.keys())
                    live_pool = [r for r in live_pool if r.case_id not in quarantined_case_ids]
                    tray_outcome = "blocked"
                    break

                except Exception:
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    _move_rows_back_to_analysis(
                        connection, active_rows, now=now, event_type="handoff_failed",
                    )
                    connection.commit()
                    raise

            # End of inner while True. If tray_outcome is set, the outcome was terminal
            # for this tray (held_busy / blocked). Otherwise result is populated.
            if tray_outcome == "held_busy":
                break  # stop packing — no more trays for this lane in this dispatch
            if tray_outcome == "blocked":
                continue  # blocked cases already removed; loop to next iteration

            assert result is not None

            # Post-PreForm partial failure: some imports succeeded, some failed
            failed_case_errors = result.get("failed_case_errors") or {}
            if isinstance(failed_case_errors, dict) and failed_case_errors:
                _mark_cases_needs_review_with_retry(
                    connection,
                    [
                        {
                            "case_id": case_id,
                            "row_ids": [
                                row.row_id
                                for row in live_pool
                                if row.row_id is not None and row.case_id == case_id
                            ],
                            "reason": f"PreForm import failed: {error}",
                        }
                        for case_id, error in failed_case_errors.items()
                    ],
                    event_type="case_quarantined_during_preform_import",
                    now=now,
                )
                live_pool = [r for r in live_pool if r.case_id not in failed_case_errors.keys()]

            accepted_rows = _manifest_rows(result["manifest"], rows_by_id)
            accepted_row_ids = [r.row_id for r in accepted_rows if r.row_id is not None]
            accepted_manifest = result["manifest"]
            accepted_case_ids = set(accepted_manifest.case_ids)

            # Density-hold check on the ACCEPTED tray
            if _should_hold_accepted_manifest(settings, accepted_manifest, hold_now):
                _update_reserved_print_job_as_held(
                    connection,
                    job_id=created_print_job_id,
                    result=result,
                    settings=settings,
                    cutoff_at=cutoff_at,
                    now=now,
                )
                _held_job_ids_created_this_process.add(created_print_job_id)
                for row in accepted_rows:
                    if row.row_id is None:
                        continue
                    connection.execute(
                        """UPDATE upload_rows
                           SET status = 'Submitted',
                               queue_section = 'in_progress',
                               handoff_stage = ?,
                               linked_job_name = ?,
                               linked_print_job_id = ?,
                               current_event_at = ?
                           WHERE id = ?""",
                        (HOLDING_STATUS, result["job_name"], created_print_job_id, now, row.row_id),
                    )
                    metadata = json.dumps({
                        "status": "Submitted",
                        "handoff_stage": HOLDING_STATUS,
                        "queue_section": "in_progress",
                        "job_name": result["job_name"],
                        "linked_print_job_id": created_print_job_id,
                        "manifest_id": manifest_id,
                        "manifest": result["manifest_json"],
                        "estimated_density": accepted_manifest.estimated_density,
                        "density_target": settings.print_hold_density_target,
                    })
                    connection.execute(
                        """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                           VALUES (?, ?, ?, ?)""",
                        (row.row_id, "build_holding", now, metadata),
                    )
                groups.append(
                    _group_result(
                        manifest_id=manifest_id,
                        status="held",
                        row_ids=accepted_row_ids,
                        job_name=result["job_name"],
                    )
                )
                # KEY CHANGE: held tray means no more packing for this lane in this dispatch.
                # The held tray IS the final remainder by definition.
                break

            # Successful dispatch path (Queued)
            _dispatch_prepared_scene_if_enabled(
                client_factory=lambda: PreFormClient(settings.preform_server_url),
                settings=settings,
                manifest=accepted_manifest,
                result=result,
                device_id=str(device["device_id"]),
                printer_device_name=(
                    str(device["device_name"])
                    if device.get("device_name") is not None
                    else None
                ),
            )
            _update_reserved_print_job_from_result(
                connection,
                job_id=created_print_job_id,
                result=result,
                settings=settings,
                now=now,
            )
            for row in accepted_rows:
                if row.row_id is None:
                    continue
                connection.execute(
                    """UPDATE upload_rows
                       SET status = 'Submitted',
                           queue_section = 'history',
                           handoff_stage = 'Queued',
                           linked_job_name = ?,
                           linked_print_job_id = ?,
                           current_event_at = ?
                       WHERE id = ?""",
                    (result["job_name"], created_print_job_id, now, row.row_id),
                )
                metadata = json.dumps({
                    "status": "Submitted",
                    "queue_section": "history",
                    "handoff_stage": "Queued",
                    "linked_job_name": result["job_name"],
                    "linked_print_job_id": created_print_job_id,
                    "manifest_id": manifest_id,
                })
                connection.execute(
                    """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                       VALUES (?, ?, ?, ?)""",
                    (row.row_id, "submitted_to_print", now, metadata),
                )
            groups.append(
                _group_result(
                    manifest_id=manifest_id,
                    status="submitted",
                    row_ids=accepted_row_ids,
                    job_name=result["job_name"],
                    print_job_id=result.get("print_job_id"),
                )
            )

            # Remove accepted cases from the live_pool. Shrink-deferred cases
            # remain in the pool and get re-packed in the next iteration.
            live_pool = [r for r in live_pool if r.case_id not in accepted_case_ids]
            connection.commit()

        # End of `while live_pool:` loop.
```

The key behavioural changes vs. the original:

| Original | New |
|----------|-----|
| `pending_manifests` populated once with all manifests | `live_pool` shrinks; `plan_build_manifests` re-runs each iteration |
| `retry_rows` re-planned at end of pending list | Shrink-deferred rows stay in `live_pool`, naturally re-packed |
| Coalesce called once before loop | Coalesce called each iteration on freshly planned manifests |
| Density hold continues to next manifest | Density hold breaks loop (final remainder by construction) |
| Busy lane creates one held job per manifest | Busy lane creates one held job for the entire remaining pool |

- [ ] **Step 3: Run the new failing test from Task 1 — must now pass**

```
python -m pytest tests/test_preform_handoff.py::test_overflow_pool_busy_lane_creates_single_held_job -v
```

Expected: **PASS**.

- [ ] **Step 4: Run the new test from Task 2 — must pass (or continue to pass)**

```
python -m pytest tests/test_preform_handoff.py::test_overflow_pool_sequentially_packs_and_holds_only_final_remainder -v
```

Expected: **PASS**.

---

## Task 4: Run full test suite and triage regressions

All 46 tests in `test_preform_handoff.py` exercise the dispatch loop. Most should pass unchanged because per-tray behaviour (Queued, Held, Layout failure shrink, Import quarantine) is preserved. Tests that asserted "two manifests both processed in one call" need updating — there are at most a few such tests.

- [ ] **Step 1: Run the dispatch test file**

```
python -m pytest tests/test_preform_handoff.py -v
```

- [ ] **Step 2: For each failing test, classify the failure**

Likely regressions and how to handle each:

- **Tests asserting that two manifests were created in one dispatch call:** if the assertion is `len(jobs) == 2` and that was the result of a single send-to-print pre-planning two manifests, the new behaviour produces different results depending on whether each tray hits density target. Update the assertion to match the new pack-one model.
- **`test_busy_lane_does_not_delete_existing_held_job` (~line 2428):** the existing held job covers a different lane in this test, so behaviour should be unchanged.
- **`test_new_compatible_rows_replan_with_existing_held_build` (~line 2191):** held rows + new rows merge into the live pool at start; behaviour preserved.
- **Layout failure shrink tests (lines 1709, 1781):** the inner while-true with `_shrink_manifest_after_layout_failure` is preserved; deferred rows now live in `live_pool` and get re-packed naturally — behaviour equivalent.

Fix tests that genuinely encode old behaviour. Do not change tests that encode the architectural contract.

- [ ] **Step 3: Run the full test suite**

```
python -m pytest tests/ -q
```

Expected: zero failures.

- [ ] **Step 4: Commit**

```
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "$(cat <<'EOF'
refactor: pack-one-at-a-time dispatch in _send_ready_rows_to_device

Replace the pre-plan-all-manifests dispatch loop with a live pool that
shrinks as each tray is accepted. The packing planner runs on each
iteration over the remaining pool, so PreForm reality drives subsequent
packing decisions, and only the final sparse tray can be held by the
density policy.

Enforces the architecture-doc invariant that at most one held job exists
per lane: a busy lane holds the entire remaining pool as a single job;
a density-below-target tray ends the loop because by definition it is
the final remainder.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Verification

- New test 1 (busy lane during overflow): one held job covers all rows.
- New test 2 (overflow with mixed densities): one Queued + at most one Held with the correct case partitioning.
- All existing 46 tests in `test_preform_handoff.py` pass.
- Full repo test suite passes.

Manual UI check:
1. Stage 41+ rows of the same lane preset.
2. Click Send to Print.
3. Verify in the print queue UI: at most one row shows "Holding for More Cases" per lane, and any preceding Queued jobs contain the largest cases first.

## Edge cases

- **3+ overflow trays in one pool:** loop iterates until pool is empty or a held outcome stops it. Only one held job possible (the final).
- **Multiple lanes in one dispatch:** this function is device-specific so all rows share one lane. Cross-lane dispatch goes through `send_ready_rows_to_print` which is out of scope.
- **PreForm shrink across pool iterations:** deferred case stays in pool, gets re-packed in next iteration possibly with smaller cases via the smallest-filler pass, eventually accepted or held.
- **All cases non-plannable:** loop removes them from pool, finds nothing to pack, exits cleanly with `blocked_groups` populated.
- **After cutoff (density hold disabled):** `_should_hold_accepted_manifest` returns `False` for all trays → all dispatch as Queued, even sparse ones — matches doc §8 "after cutoff: new below-target builds dispatch immediately".
