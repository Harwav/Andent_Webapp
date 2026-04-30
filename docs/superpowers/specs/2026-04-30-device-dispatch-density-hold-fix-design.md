# Device Dispatch Density Hold Fix

**Date:** 2026-04-30
**Status:** Draft

---

## Problem

The device-based dispatch path (`_send_ready_rows_to_device`) in `print_queue_service.py` was implemented for the multi-select local printer feature but **never received the density-based holding check**. The original non-device path (`send_ready_rows_to_print` with `device_id=None`) correctly calls `_should_hold_manifest()` to hold below-target builds. The device path skips this entirely, sending every planned manifest straight to PreFormServer scene creation regardless of density.

This caused `260430_0004` and any other low-density build dispatched via a selected printer to be sent immediately instead of being held.

## Holding Policy (from `2026-04-24-preset-printer-hold-policy-design.md`)

- Density target: `40%` (configurable via `ANDENT_WEB_PRINT_HOLD_DENSITY_TARGET`)
- Cutoff time: `18:00` local (configurable via `ANDENT_WEB_PRINT_HOLD_CUTOFF_LOCAL_TIME`)
- Only the **final** below-target build per compatibility group is held
- At cutoff, held builds dispatch anyway
- Operator can manually "Release now" before cutoff

## Fix

### Location

`app/services/print_queue_service.py`, function `_send_ready_rows_to_device`, lines ~1565-1777.

### Change

Insert the same hold gate that exists in the original path (lines 1960-2017) into the device dispatch manifest loop. The loop currently looks like:

```python
for manifest in manifests:
    # ... non_plannable check (lines 1568-1595) ...
    
    active_rows = _manifest_rows(manifest, rows_by_id)
    job_name = _generate_unique_job_name_for_manifest(...)
    created_print_job_id = _reserve_print_job_for_rows(...)
    # ... process_print_manifest immediately ...
```

After the non_plannable check and before `_reserve_print_job_for_rows`, add:

```python
if _should_hold_manifest(
    settings,
    manifest,
    manifest_index,
    final_index_by_compatibility,
    hold_now,
):
    job_name = _generate_unique_job_name_for_manifest(
        connection,
        datetime.now(),
        manifest,
    )
    held_job = _held_print_job_from_manifest(
        settings,
        manifest,
        job_name,
        cutoff_at,
    )
    created_print_job_id = _insert_print_job(connection, held_job, now)
    _held_job_ids_created_this_process.add(created_print_job_id)
    for row in manifest_rows:
        connection.execute(
            """
            UPDATE upload_rows
            SET status = 'Submitted',
                queue_section = 'in_progress',
                handoff_stage = ?,
                linked_job_name = ?,
                linked_print_job_id = ?,
                current_event_at = ?
            WHERE id = ?
            """,
            (
                HOLDING_STATUS,
                job_name,
                created_print_job_id,
                now,
                row.row_id,
            ),
        )
        metadata = json.dumps({
            "status": "Submitted",
            "queue_section": "in_progress",
            "handoff_stage": HOLDING_STATUS,
            "job_name": job_name,
            "linked_print_job_id": created_print_job_id,
            "manifest": manifest.model_dump(),
            "estimated_density": manifest.estimated_density,
            "density_target": settings.print_hold_density_target,
        })
        connection.execute(
            """
            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (row.row_id, "build_holding", now, metadata),
        )
    continue
```

### Required Setup Variables

The following variables need to be computed before the manifest loop (same as the original path):

```python
hold_now = _now()
cutoff_at = _parse_cutoff_today(settings.print_hold_cutoff_local_time, hold_now)
final_index_by_compatibility: dict[str | None, int] = {}
for index, manifest in enumerate(manifests):
    if manifest.planning_status == "planned":
        final_index_by_compatibility[manifest.compatibility_key] = index
```

### Group Result for Held Builds

Held builds should also appear in the response `groups` array with status `"held"` so the frontend can report them:

```python
groups.append(
    _group_result(
        manifest_id=manifest_id,
        status="held",
        row_ids=manifest_row_id_list,
        job_name=job_name,
    )
)
```

## Test

Add one test to `tests/test_preform_handoff.py`:

```python
def test_selected_device_send_to_print_holds_final_below_target_build(tmp_path):
    """Device dispatch path must respect density-based holding, same as non-device path."""
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "device-hold-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-DEVICE-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "held"
    assert stub_client.created_scenes == []  # No scene created — build is held
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].printer_device_id == "form-4bl-lab"
```

## Files Changed

| File | Change |
|---|---|
| `app/services/print_queue_service.py` | Add hold gate to `_send_ready_rows_to_device` manifest loop |
| `tests/test_preform_handoff.py` | Add `test_selected_device_send_to_print_holds_final_below_target_build` |

## Risk Assessment

- **Low risk**: The hold logic is identical to the proven original path. Only the insertion point differs.
- **No API contract change**: The response shape gains a `"held"` status in `groups`, which is additive.
- **No frontend change needed**: The existing "Holding for More Cases" display logic already handles this status.
