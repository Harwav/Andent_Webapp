# Busy Lane Queue Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow new files to join an existing printer/material/layer lane while preventing more than one active PreForm build-prep operation for that lane.

**Architecture:** Split the current send-to-print flow into queue intake and active build preparation. A busy build lane should create or preserve a held queue entry instead of treating the request as a handoff failure, and row rollback to File Analysis should remain reserved for real PreForm/import/layout/dispatch failures.

**Tech Stack:** FastAPI, SQLite, Pydantic, vanilla JavaScript, pytest.

---

## File Structure

- Modify `app/services/print_queue_service.py`
  - Add a typed lane-busy exception.
  - Change lane-lock acquisition so contention can be handled as a queue-intake result.
  - Move held-job deletion so it only happens after active prep lock acquisition.
  - Add a helper to hold newly submitted rows when the lane is busy.
- Modify `tests/test_preform_handoff.py`
  - Replace the existing same-lane-lock rejection expectation.
  - Add regression coverage that busy-lane rows stay in `in_progress`, not `analysis`.
  - Preserve existing coverage that different lanes can still prep independently.
- Modify `app/static/app.js`
  - Add a global client-side send guard so duplicate clicks or re-renders cannot fire overlapping send requests from the same browser session.
- Modify `tests/test_frontend_static.py`
  - Add static checks for the send guard and disabled state.

## Design Rules

- "Join the queue" is allowed even when the lane is busy.
- "Start active build prep" is exclusive per lane.
- A lane-busy condition is not a handoff failure.
- A lane-busy condition must not call `_move_rows_back_to_analysis()`.
- Existing held queue entries must not be deleted unless the code has acquired the active prep lock and is actually replanning them.

---

### Task 1: Lock the Busy-Lane Behavior With Backend Tests

**Files:**
- Modify: `tests/test_preform_handoff.py`

- [ ] **Step 1: Replace the current rejection test with the desired behavior**

Find `test_send_to_print_rejects_when_same_build_lane_is_locked` in `tests/test_preform_handoff.py` and replace it with:

```python
def test_send_to_print_holds_rows_when_same_build_lane_is_busy(tmp_path):
    from app.database import get_upload_row_by_id, try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "busy-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-BUSY-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-busy-lane",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_ids[0])]
    lane_key = _build_lane_keys_from_manifests(
        plan_build_manifests(rows),
        device_id="form-4bl-lab",
    )[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "test-owner", "send")

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {
            "id": "form-4bl-lab",
            "name": "Lab Printer",
            "model": "Form 4BL",
            "status": "Ready",
            "is_virtual": True,
        }
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "held"
    assert "already preparing" in payload["groups"][0]["error"].lower()
    assert stub_client.imported_models == []
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].case_ids == ["CASE-BUSY-LANE"]

    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Submitted"
    assert row.queue_section == "in_progress"
    assert row.handoff_stage == "Holding for More Cases"
    assert row.linked_print_job_id == jobs[0].id

    with closing(connect(settings)) as connection:
        events = connection.execute(
            """
            SELECT event_type, metadata_json
            FROM upload_row_events
            WHERE row_id = ?
            ORDER BY id
            """,
            (row_ids[0],),
        ).fetchall()
    assert [event["event_type"] for event in events] == ["created", "build_holding"]
    assert not any(event["event_type"] == "handoff_failed" for event in events)
```

- [ ] **Step 2: Add a regression test for preserving existing held rows when the lane is busy**

Add this test near the existing held-replan tests:

```python
def test_busy_lane_does_not_delete_existing_held_job(tmp_path):
    from app.database import get_upload_row_by_id, try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = replace(_build_settings(tmp_path), print_hold_density_target=0.95)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "held.stl"
    held_file.write_text("solid held\nendsolid held\n", encoding="utf-8")
    held_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-ALREADY-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-already-held",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {
            "id": "form-4bl-lab",
            "name": "Lab Printer",
            "model": "Form 4BL",
            "status": "Ready",
            "is_virtual": True,
        }
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": held_ids, "device_id": "form-4bl-lab"},
        )

    assert first_response.status_code == 200
    existing_job = list_print_jobs(settings)[0]
    assert existing_job.status == "Holding for More Cases"

    new_file = tmp_path / "new-compatible.stl"
    new_file.write_text("solid new\nendsolid new\n", encoding="utf-8")
    new_ids = _seed_rows(
        settings,
        [
            _row_payload(
                new_file,
                case_id="CASE-NEW-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-new-held",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )
    new_rows = [get_upload_row_by_id(settings, new_ids[0])]
    lane_key = _build_lane_keys_from_manifests(
        plan_build_manifests(new_rows),
        device_id="form-4bl-lab",
    )[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "external-prep", "send")

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": new_ids, "device_id": "form-4bl-lab"},
        )

    assert second_response.status_code == 200
    jobs = list_print_jobs(settings)
    assert {job.status for job in jobs} == {"Holding for More Cases"}
    assert {case_id for job in jobs for case_id in job.case_ids} == {
        "CASE-ALREADY-HELD",
        "CASE-NEW-HELD",
    }
    assert get_upload_row_by_id(settings, held_ids[0]).queue_section == "in_progress"
    assert get_upload_row_by_id(settings, new_ids[0]).queue_section == "in_progress"
```

- [ ] **Step 3: Run the new tests and verify they fail for the right reason**

Run:

```powershell
pytest tests/test_preform_handoff.py::test_send_to_print_holds_rows_when_same_build_lane_is_busy tests/test_preform_handoff.py::test_busy_lane_does_not_delete_existing_held_job -q
```

Expected before implementation:

```text
FAILED ... assert response.status_code == 200
```

or equivalent evidence that the current code still treats the busy lane as a rejection/rollback path.

---

### Task 2: Implement Busy-Lane Queue Intake

**Files:**
- Modify: `app/services/print_queue_service.py`

- [ ] **Step 1: Add a lane-busy exception**

Near `DeviceDispatchValidationError`, add:

```python
class BuildLaneBusyError(ValueError):
    """Raised when active build prep is already running for a lane."""
```

- [ ] **Step 2: Make `_build_lane_locks` raise the typed exception**

Replace the `raise ValueError(...)` block inside `_build_lane_locks` with:

```python
            raise BuildLaneBusyError(
                "Build preparation is already in progress for this printer/material/layer lane. "
                "The selected files were queued for the next compatible build."
            )
```

- [ ] **Step 3: Add a helper to hold rows without PreForm prep**

Add this helper near `_reserve_print_job_for_rows`:

```python
def _hold_rows_for_busy_build_lane(
    connection,
    *,
    settings: "Settings",
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    job_name: str,
    now: str,
    cutoff_at: datetime,
    device_id: str | None,
    printer_device_name: str | None,
) -> int:
    held_job = _held_print_job_from_manifest(
        settings,
        manifest,
        job_name,
        cutoff_at,
        device_id=device_id,
        printer_device_name=printer_device_name,
    )
    created_print_job_id = _insert_print_job(connection, held_job, now)
    _held_job_ids_created_this_process.add(created_print_job_id)
    for row in rows:
        if row.row_id is None:
            continue
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
            "reason": "active_build_lane_busy",
        })
        connection.execute(
            """
            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (row.row_id, "build_holding", now, metadata),
        )
    return created_print_job_id
```

- [ ] **Step 4: Move held-job deletion inside active prep acquisition**

In `_send_ready_rows_to_device`, remove the early block that deletes `held_job_ids` before `planning_rows` is built:

```python
        if held_job_ids:
            connection.execute(
                f"""
                DELETE FROM print_jobs
                WHERE id IN ({",".join("?" for _ in held_job_ids)})
                """,
                tuple(held_job_ids),
            )
            for held_job_id in held_job_ids:
                _held_job_ids_created_this_process.discard(held_job_id)
```

Later, only after the lane lock has been acquired for active prep, delete those held jobs. Put this inside the `with _build_lane_locks(...)` body before `process_print_manifest(...)`:

```python
                        if held_job_ids:
                            connection.execute(
                                f"""
                                DELETE FROM print_jobs
                                WHERE id IN ({",".join("?" for _ in held_job_ids)})
                                """,
                                tuple(held_job_ids),
                            )
                            for held_job_id in held_job_ids:
                                _held_job_ids_created_this_process.discard(held_job_id)
```

- [ ] **Step 5: Acquire the lane lock before reserving active rows**

In the active dispatch loop around `active_rows = _manifest_rows(...)`, replace the current order:

```python
created_print_job_id = _reserve_print_job_for_rows(...)
connection.commit()
with _build_lane_locks(...):
    result = process_print_manifest(...)
```

with this shape:

```python
lane_key = _build_lane_key_from_manifest(
    active_manifest,
    device_id=str(device["device_id"]),
)
try:
    with _build_lane_locks(
        settings,
        [lane_key],
        operation="send_to_print",
    ):
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
        if held_job_ids:
            connection.execute(
                f"""
                DELETE FROM print_jobs
                WHERE id IN ({",".join("?" for _ in held_job_ids)})
                """,
                tuple(held_job_ids),
            )
            for held_job_id in held_job_ids:
                _held_job_ids_created_this_process.discard(held_job_id)
        result = process_print_manifest(
            settings,
            active_manifest,
            active_rows,
            batch_number=1,
            job_name=job_name,
            device_id=str(device["device_id"]),
            printer_device_name=(
                str(device["device_name"])
                if device.get("device_name") is not None
                else None
            ),
            dispatch_scene=False,
        )
    break
except BuildLaneBusyError as exc:
    created_print_job_id = _hold_rows_for_busy_build_lane(
        connection,
        settings=settings,
        manifest=active_manifest,
        rows=active_rows,
        job_name=job_name,
        now=now,
        cutoff_at=cutoff_at,
        device_id=str(device["device_id"]),
        printer_device_name=(
            str(device["device_name"])
            if device.get("device_name") is not None
            else None
        ),
    )
    connection.commit()
    groups.append(
        _group_result(
            manifest_id=manifest_id,
            status="held",
            row_ids=[row.row_id for row in active_rows if row.row_id is not None],
            job_name=job_name,
            error=str(exc),
        )
    )
    result = None
    break
```

Keep the existing `except PreFormAutoLayoutFailureError`, `except PreFormImportFailureError`, and generic `except Exception` branches for real handoff failures after active prep starts.

- [ ] **Step 6: Keep the payload successful when all groups are held**

At the end of `_send_ready_rows_to_device`, keep this behavior:

```python
if not groups:
    ...
    raise DeviceDispatchValidationError(payload, status_code=status_code)
return payload
```

Because the busy-lane path appends a `held` group, it should return HTTP 200 with a held group instead of 409/422/502.

- [ ] **Step 7: Run the backend regression tests**

Run:

```powershell
pytest tests/test_preform_handoff.py::test_send_to_print_holds_rows_when_same_build_lane_is_busy tests/test_preform_handoff.py::test_busy_lane_does_not_delete_existing_held_job -q
```

Expected:

```text
2 passed
```

---

### Task 3: Add the Frontend Duplicate Submit Guard

**Files:**
- Modify: `app/static/app.js`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add frontend static tests**

Add this test to `tests/test_frontend_static.py`:

```python
def test_send_to_print_uses_global_submit_guard():
    app_js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert "sendToPrintInFlight: false" in app_js
    assert "state.sendToPrintInFlight = true;" in app_js
    assert "state.sendToPrintInFlight = false;" in app_js
    assert "if (state.sendToPrintInFlight)" in app_js
    assert "submitButton.disabled = !readyToSend || state.sendToPrintInFlight;" in app_js
```

- [ ] **Step 2: Run the frontend static test and verify it fails**

Run:

```powershell
pytest tests/test_frontend_static.py::test_send_to_print_uses_global_submit_guard -q
```

Expected before implementation:

```text
FAILED ... assert 'sendToPrintInFlight: false' in app_js
```

- [ ] **Step 3: Add state for global submit in-flight**

In `app/static/app.js`, inside the top-level `state` object near `bulkPrinterValue`, add:

```javascript
    sendToPrintInFlight: false,
```

- [ ] **Step 4: Disable the send button while any send is running**

Replace:

```javascript
        submitButton.disabled = !readyToSend;
```

with:

```javascript
        submitButton.disabled = !readyToSend || state.sendToPrintInFlight;
```

- [ ] **Step 5: Guard `sendRowsToPrint`**

At the top of `sendRowsToPrint(rows, deviceId)`, after the `deviceId` check, add:

```javascript
    if (state.sendToPrintInFlight) {
        setStatus("A send-to-print request is already running.", true);
        return false;
    }
    state.sendToPrintInFlight = true;
```

In the `finally` block, replace:

```javascript
        window.pollingPaused = false;
```

with:

```javascript
        state.sendToPrintInFlight = false;
        window.pollingPaused = false;
        render();
```

- [ ] **Step 6: Run the frontend static test**

Run:

```powershell
pytest tests/test_frontend_static.py::test_send_to_print_uses_global_submit_guard -q
```

Expected:

```text
1 passed
```

---

### Task 4: Run Focused and Full Verification

**Files:**
- No additional edits.

- [ ] **Step 1: Run focused handoff and frontend tests**

Run:

```powershell
pytest tests/test_preform_handoff.py::test_send_to_print_holds_rows_when_same_build_lane_is_busy tests/test_preform_handoff.py::test_busy_lane_does_not_delete_existing_held_job tests/test_preform_handoff.py::test_selected_device_new_compatible_rows_replan_with_existing_held_build tests/test_frontend_static.py::test_send_to_print_uses_global_submit_guard -q
```

Expected:

```text
4 passed
```

- [ ] **Step 2: Run the broader related test files**

Run:

```powershell
pytest tests/test_preform_handoff.py tests/test_print_queue.py tests/test_print_queue_polling.py tests/test_frontend_static.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run the full test suite**

Run:

```powershell
pytest tests/ -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run live PreFormServer verification**

Start or reuse the local server, then verify health and PreForm readiness:

```powershell
uvicorn app.main:app --reload --port 8090
```

In another shell:

```powershell
curl http://localhost:8090/health
curl http://localhost:8090/api/preform-setup/status
curl http://localhost:8090/api/uploads/queue
curl http://localhost:8090/api/print-queue/jobs
```

Expected:

```text
/health returns 200
PreForm status readiness is ready
uploads queue returns 200
print queue returns 200
```

Then manually exercise:

1. Start one same-lane send-to-print batch.
2. While it is preparing, send another compatible same-lane batch.
3. Confirm the second batch appears as held/queued, not File Analysis.
4. Confirm no `handoff_failed` events are recorded for the busy-lane batch.

---

## Self-Review

- Spec coverage: The plan covers backend lock contention, held queue preservation, frontend duplicate submits, regression tests, and live PreForm verification.
- Placeholder scan: No placeholder tasks are left; every edit has a target file and concrete code.
- Type consistency: The plan uses existing names from the codebase: `HOLDING_STATUS`, `_held_print_job_from_manifest`, `_insert_print_job`, `_group_result`, `_build_lane_locks`, `DeviceDispatchValidationError`, and `BuildLaneBusyError`.
- Scope check: This is one focused behavior change. It avoids unrelated queue redesign and does not introduce new dependencies.
