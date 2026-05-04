# Build Lane Concurrency And Density Hold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate held builds and underpacked queued builds by serializing build preparation per compatible tray lane and rechecking density after PreForm accepts or rejects cases.

**Architecture:** Add a small SQLite-backed build-lane lock so only one build-prep operation can run for the same compatible tray lane at a time. Keep different lanes concurrent. Split PreForm preparation from printer dispatch so the app can recompute final accepted density and hold the tray before sending it to a selected printer.

**Tech Stack:** Python 3.9+, FastAPI, SQLite, pytest, existing `tests/test_preform_handoff.py` PreForm stubs.

---

## File Structure

- Modify `app/database.py`
  - Add `build_lane_locks` table.
  - Add lock acquire/release helpers.
  - Keep lock state out of `print_jobs` because locks are transient runtime coordination, not job history.
- Modify `app/schemas.py`
  - No required schema change unless implementation chooses to expose `build_lane_key` in `PrintJob`. Default plan keeps lane keys internal.
- Modify `app/services/print_queue_service.py`
  - Add lane-key helpers.
  - Wrap send-to-print and held release flows in per-lane locks.
  - Recompute subset manifest density.
  - Split tray preparation from selected-printer dispatch.
  - Reapply hold decision after PreForm import quarantine/layout recovery.
- Modify `tests/test_print_queue.py`
  - Add database lock helper coverage.
- Modify `tests/test_preform_handoff.py`
  - Add regressions for same-lane conflict, different-lane concurrency allowance, post-import under-density hold, and selected-device no-dispatch-before-hold.
- Optional modify `.codex/skills/formflow-release/SKILL.md`
  - Only if packaged verification checklist needs updated proof steps.

---

## Lane Contract

Build lane key:

```text
target|printer_group|material_code|material_label|layer_height_microns|print_setting
```

Where:

- `target` is `device:<selected_device_id>` when a physical device is selected.
- `target` is `group:<printer_group>` when dispatch is not device-specific.
- Same raw preset name is not required. Multiple compatible presets may share a lane when they share printer, resin/material, layer height, and print settings.
- Compatibility should stay based on the existing `BuildManifest` fields and `compatibility_key`.

Operational rules:

- Same lane: one active build preparation or held release at a time.
- Different lane: can prepare concurrently.
- Held build merge must only load existing held rows from compatible lanes.
- If PreForm rejects cases and the accepted manifest falls below density target, the accepted build is held before printer dispatch.
- A selected-device flow must not call PreForm `/print/` until post-PreForm density is known.

---

### Task 1: Add SQLite Build-Lane Lock Primitives

**Files:**
- Modify: `app/database.py:23-138`
- Modify: `app/database.py:252-309`
- Test: `tests/test_print_queue.py`

- [ ] **Step 1: Add the lock table and index**

In `app/database.py`, add this schema statement to `SCHEMA_STATEMENTS` after the `preform_setup_state` table:

```python
    """
    CREATE TABLE IF NOT EXISTS build_lane_locks (
        lane_key TEXT PRIMARY KEY,
        owner_token TEXT NOT NULL,
        operation TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
```

Add this index to `INDEX_STATEMENTS`:

```python
    """
    CREATE INDEX IF NOT EXISTS ix_build_lane_locks_expires_at
    ON build_lane_locks(expires_at)
    """,
```

- [ ] **Step 2: Add lock helper functions**

In `app/database.py`, add these imports near the existing imports:

```python
from datetime import datetime, timedelta, timezone
```

If `datetime` and `timezone` are already imported, only add `timedelta`.

Add these helpers below `connect()`:

```python
BUILD_LANE_LOCK_TTL_MINUTES = 120


def _parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def try_acquire_build_lane_lock(
    settings: Settings,
    lane_key: str,
    owner_token: str,
    operation: str,
    *,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(timezone.utc)
    acquired_at = current.isoformat()
    expires_at = (current + timedelta(minutes=BUILD_LANE_LOCK_TTL_MINUTES)).isoformat()
    with closing(connect(settings)) as connection:
        connection.execute(
            "DELETE FROM build_lane_locks WHERE expires_at <= ?",
            (acquired_at,),
        )
        try:
            connection.execute(
                """
                INSERT INTO build_lane_locks (lane_key, owner_token, operation, acquired_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lane_key, owner_token, operation, acquired_at, expires_at),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return False
        connection.commit()
        return True


def release_build_lane_lock(
    settings: Settings,
    lane_key: str,
    owner_token: str,
) -> None:
    with closing(connect(settings)) as connection:
        connection.execute(
            """
            DELETE FROM build_lane_locks
            WHERE lane_key = ? AND owner_token = ?
            """,
            (lane_key, owner_token),
        )
        connection.commit()
```

- [ ] **Step 3: Add lock primitive tests**

Append these tests to `tests/test_print_queue.py`:

```python
from datetime import datetime, timedelta, timezone

from app.database import (
    release_build_lane_lock,
    try_acquire_build_lane_lock,
)


def test_build_lane_lock_blocks_same_lane_until_released(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1", "send")
    assert not try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")

    release_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1")

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")


def test_build_lane_lock_allows_different_lanes(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1", "send")
    assert try_acquire_build_lane_lock(settings, "device:B|form4bl|pm|100", "owner-2", "send")
    assert try_acquire_build_lane_lock(settings, "group:Form 4B|lt-clear|100", "owner-3", "send")


def test_build_lane_lock_replaces_expired_lock(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)
    old_now = datetime.now(timezone.utc) - timedelta(hours=3)

    assert try_acquire_build_lane_lock(
        settings,
        "device:A|form4bl|pm|100",
        "owner-1",
        "send",
        now=old_now,
    )

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")
```

- [ ] **Step 4: Run lock tests and verify they fail before implementation**

Run:

```bash
python -m pytest tests/test_print_queue.py::test_build_lane_lock_blocks_same_lane_until_released tests/test_print_queue.py::test_build_lane_lock_allows_different_lanes tests/test_print_queue.py::test_build_lane_lock_replaces_expired_lock -q
```

Expected before implementation: FAIL due to missing lock helpers/table.

- [ ] **Step 5: Run lock tests and verify they pass**

Run the same command.

Expected after implementation: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/database.py tests/test_print_queue.py
git commit -m "Serialize build preparation by durable lane locks"
```

Lore body:

```text
Build preparation can overlap through FastAPI threadpool dispatch, so same-lane operations need a database-visible guard before PreForm work starts. The lock is transient and expires to recover from interrupted packaged runs.

Constraint: No new dependencies; SQLite remains the local coordination surface
Rejected: In-process threading.Lock only | does not protect restart recovery or future multi-process packaging
Confidence: high
Scope-risk: moderate
Tested: Build lane lock pytest coverage
```

---

### Task 2: Add Build Lane Key Helpers

**Files:**
- Modify: `app/services/print_queue_service.py:560-640`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Add lane-key helpers**

In `app/services/print_queue_service.py`, add these imports near the top:

```python
from contextlib import contextmanager
from uuid import uuid4
```

Add these helpers near `DeviceDispatchValidationError`:

```python
def _lane_part(value: object) -> str:
    text = str(value or "unknown").strip() or "unknown"
    return text.replace("|", "/").lower()


def _manifest_layer_height_microns(manifest: "BuildManifest") -> str:
    if manifest.layer_thickness_mm is None:
        return "unknown"
    return str(int(round(float(manifest.layer_thickness_mm) * 1000)))


def _build_lane_key_from_manifest(
    manifest: "BuildManifest",
    *,
    device_id: str | None = None,
) -> str:
    target = f"device:{device_id}" if device_id else f"group:{manifest.printer_group or 'unknown'}"
    return "|".join(
        [
            _lane_part(target),
            _lane_part(manifest.printer_group),
            _lane_part(manifest.material_code),
            _lane_part(manifest.material_label),
            _manifest_layer_height_microns(manifest),
            _lane_part(manifest.print_setting),
        ]
    )


def _build_lane_keys_from_manifests(
    manifests: list["BuildManifest"],
    *,
    device_id: str | None = None,
) -> list[str]:
    lane_keys = {
        _build_lane_key_from_manifest(manifest, device_id=device_id)
        for manifest in manifests
        if manifest.planning_status == "planned" and manifest.import_groups
    }
    return sorted(lane_keys)
```

- [ ] **Step 2: Add lane-key tests**

Append these tests to `tests/test_preform_handoff.py`:

```python
def test_build_lane_key_merges_compatible_presets_in_same_material_lane(tmp_path):
    from app.database import get_upload_row_by_id
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    model_file = tmp_path / "model.stl"
    tooth_file = tmp_path / "tooth.stl"
    for file_path in (model_file, tooth_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                model_file,
                case_id="CASE-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-lane-model",
            ),
            _row_payload(
                tooth_file,
                case_id="CASE-LANE",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-lane-tooth",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_id) for row_id in row_ids]
    manifests = plan_build_manifests(rows)

    lane_keys = _build_lane_keys_from_manifests(manifests)

    assert len(lane_keys) == 1
    assert "form 4bl" in lane_keys[0]
    assert "precision model" in lane_keys[0]
    assert "|100|" in lane_keys[0]


def test_build_lane_key_splits_selected_devices_for_same_material_lane(tmp_path):
    from app.database import get_upload_row_by_id
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    case_file = tmp_path / "device-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-DEVICE-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-lane",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_ids[0])]
    manifests = plan_build_manifests(rows)

    east = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-east")
    west = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-west")

    assert east != west
    assert east[0].startswith("device:form-4bl-east|")
    assert west[0].startswith("device:form-4bl-west|")
```

- [ ] **Step 3: Run lane-key tests**

Run:

```bash
python -m pytest tests/test_preform_handoff.py::test_build_lane_key_merges_compatible_presets_in_same_material_lane tests/test_preform_handoff.py::test_build_lane_key_splits_selected_devices_for_same_material_lane -q
```

Expected: PASS after helper implementation.

- [ ] **Step 4: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "Derive build lanes from compatible tray settings"
```

Lore body:

```text
Build serialization must follow tray compatibility, not raw preset names. Lane keys now group presets that share printer, material, layer height, and print setting while splitting explicit physical printer targets.

Constraint: Tooth and ortho presets can share a Form 4BL Precision Model 100um tray
Rejected: Use preset name as lane key | would prevent compatible mixed-preset builds
Confidence: high
Scope-risk: narrow
Tested: Lane-key pytest coverage
```

---

### Task 3: Lock Send-To-Print And Held Release By Lane

**Files:**
- Modify: `app/services/print_queue_service.py:560-640`
- Modify: `app/services/print_queue_service.py:1729-2185`
- Modify: `app/services/print_queue_service.py:2223-2657`
- Modify: `app/services/print_queue_service.py:2662-2824`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Add a lock context manager**

Add this helper below `_build_lane_keys_from_manifests()`:

```python
@contextmanager
def _build_lane_locks(
    settings: "Settings",
    lane_keys: list[str],
    *,
    operation: str,
):
    from ..database import release_build_lane_lock, try_acquire_build_lane_lock

    owner_token = uuid4().hex
    acquired: list[str] = []
    try:
        for lane_key in sorted(set(lane_keys)):
            if try_acquire_build_lane_lock(settings, lane_key, owner_token, operation):
                acquired.append(lane_key)
                continue
            raise ValueError(
                "Build preparation is already in progress for this printer/material/layer lane. "
                "Wait for the current build to finish or hold, then try again."
            )
        yield
    finally:
        for lane_key in reversed(acquired):
            release_build_lane_lock(settings, lane_key, owner_token)
```

- [ ] **Step 2: Wrap selected-device dispatch**

In `_send_ready_rows_to_device()`, after `manifests = plan_build_manifests(...)` and before any `DELETE FROM print_jobs` or row updates, compute lane keys:

```python
        lane_keys = _build_lane_keys_from_manifests(
            manifests,
            device_id=str(device["device_id"]),
        )
```

Then wrap the existing DB transaction and manifest loop with:

```python
    with _build_lane_locks(settings, lane_keys, operation="send_to_print"):
        with closing(connect(settings)) as connection:
            ...
```

Keep the existing transaction body inside the lock block. Do not hold a SQLite transaction open solely for the lane lock; the lock is represented by the committed `build_lane_locks` row.

- [ ] **Step 3: Wrap default dispatch**

In `send_ready_rows_to_print()`, after `manifests = plan_build_manifests(...)` and before `with closing(connect(settings)) as connection:`, add:

```python
    lane_keys = _build_lane_keys_from_manifests(manifests)
```

Wrap the existing DB transaction and manifest loop with:

```python
    with _build_lane_locks(settings, lane_keys, operation="send_to_print"):
        with closing(connect(settings)) as connection:
            ...
```

- [ ] **Step 4: Wrap held release**

In `release_held_print_job()`, after validating the job and building `manifest`, compute:

```python
    lane_key = _build_lane_key_from_manifest(
        manifest,
        device_id=job.printer_device_id,
    )
```

Wrap the PreForm release processing and DB update with:

```python
    with _build_lane_locks(settings, [lane_key], operation="release_held"):
        result = process_print_manifest(...)
        ...
```

- [ ] **Step 5: Add same-lane conflict test**

Append this test to `tests/test_preform_handoff.py`:

```python
def test_send_to_print_rejects_when_same_build_lane_is_locked(tmp_path):
    from app.database import try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "locked-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-LOCKED-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-locked-lane",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_ids[0])]
    lane_key = _build_lane_keys_from_manifests(plan_build_manifests(rows))[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "test-owner", "send")

    with patch("app.services.preform_setup_service.get_preform_setup_status", return_value=_ready_setup_status(settings)):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 409
    assert "Build preparation is already in progress" in response.json()["detail"]
    assert list_print_jobs(settings) == []
```

- [ ] **Step 6: Add different-lane allowed test**

Append this test to `tests/test_preform_handoff.py`:

```python
def test_send_to_print_allows_different_material_lane_while_other_lane_locked(tmp_path):
    from app.database import try_acquire_build_lane_lock

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "unlocked-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-UNLOCKED-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-unlocked-lane",
            ),
        ],
    )

    assert try_acquire_build_lane_lock(
        settings,
        "group:form 4b|form 4b|lt-clear|lt clear|100|default",
        "test-owner",
        "send",
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert len(list_print_jobs(settings)) == 1
```

- [ ] **Step 7: Run lane lock integration tests**

Run:

```bash
python -m pytest tests/test_preform_handoff.py::test_send_to_print_rejects_when_same_build_lane_is_locked tests/test_preform_handoff.py::test_send_to_print_allows_different_material_lane_while_other_lane_locked -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "Guard build handoff with compatible lane locks"
```

Lore body:

```text
FastAPI can run multiple send-to-print requests in the threadpool, but held-build decisions are only correct when same-lane planning sees the latest committed state. Build handoff and held release now take a committed lane lock before mutating jobs or calling PreForm.

Constraint: Different printer/material/layer lanes must remain concurrent
Rejected: Global app-wide lock | unnecessarily blocks incompatible trays
Confidence: high
Scope-risk: moderate
Tested: Same-lane conflict and different-lane allowance tests
```

---

### Task 4: Recompute Manifest Metrics After Every Subset

**Files:**
- Modify: `app/services/print_queue_service.py:704-749`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Add the metric helper**

Add this helper immediately above `_subset_manifest()`:

```python
def _manifest_used_xy_budget(manifest: "BuildManifest") -> float:
    return sum(
        float(file_spec.xy_footprint_estimate or 0.0)
        for group in manifest.import_groups
        for file_spec in group.files
    )
```

- [ ] **Step 2: Update `_subset_manifest()` to recalculate density**

Replace the return block of `_subset_manifest()` with:

```python
    updated_manifest = manifest.model_copy(
        update={
            "case_ids": case_ids,
            "preset_names": sorted(set(preset_names)),
            "import_groups": import_groups,
        }
    )
    used_xy_budget = _manifest_used_xy_budget(updated_manifest)
    printer_xy_budget = float(updated_manifest.printer_xy_budget or 0.0)
    estimated_density = used_xy_budget / printer_xy_budget if printer_xy_budget else 0.0
    return updated_manifest.model_copy(
        update={
            "used_xy_budget": used_xy_budget,
            "estimated_density": estimated_density,
        }
    )
```

- [ ] **Step 3: Add or keep the import-quarantine density test**

Ensure `tests/test_preform_handoff.py` contains:

```python
def test_import_quarantine_recomputes_manifest_density_for_accepted_cases(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "accepted.stl"
    broken_file = tmp_path / "broken.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 50.0, 40.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-ACCEPTED",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-accepted",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-BROKEN",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-broken",
                dimension_x_mm=50.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "broken.stl")
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].case_ids == ["CASE-ACCEPTED"]
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].manifest_json["used_xy_budget"] == 1200.0
    assert jobs[0].manifest_json["estimated_density"] == 1200.0 / 69188.0

    broken_row = get_upload_row_by_id(settings, row_ids[1])
    assert broken_row is not None
    assert broken_row.status == "Needs Review"
    assert "Broken model" in (broken_row.review_reason or "")
```

- [ ] **Step 4: Run the regression**

Run:

```bash
python -m pytest tests/test_preform_handoff.py::test_import_quarantine_recomputes_manifest_density_for_accepted_cases -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "Keep manifest density accurate after case removal"
```

Lore body:

```text
PreForm can reject damaged cases after the planner accepted a manifest. Any subset manifest now recomputes footprint and density from surviving file specs so queue records and hold decisions reflect the actual accepted tray.

Rejected: Recompute only during import failure handling | layout shrink and validation rollback also subset manifests
Confidence: high
Scope-risk: narrow
Tested: Import-quarantine density regression
```

---

### Task 5: Hold Under-Target Accepted Manifests Before Dispatch

**Files:**
- Modify: `app/services/print_queue_service.py:597-626`
- Modify: `app/services/print_queue_service.py:995-1167`
- Modify: `app/services/print_queue_service.py:1417-1479`
- Modify: `app/services/print_queue_service.py:1976-2175`
- Modify: `app/services/print_queue_service.py:2436-2654`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Add a `dispatch_scene` flag to `process_print_manifest()`**

Change the function signature to:

```python
def process_print_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    batch_number: int,
    job_name: str | None = None,
    device_id: str | None = None,
    printer_device_name: str | None = None,
    *,
    dispatch_scene: bool = True,
) -> dict:
```

Replace the `_dispatch_scene_if_enabled()` call with:

```python
        print_job_id = _dispatch_scene_if_enabled(
            client=client,
            settings=settings,
            scene_id=scene_id,
            manifest=manifest,
            rows=active_rows,
            job_name=job_name,
            device_id=device_id,
            force_dispatch=(device_id is not None and dispatch_scene),
        )
```

- [ ] **Step 2: Add a helper to dispatch a prepared scene after hold checks**

Add this helper near `_dispatch_scene_if_enabled()`:

```python
def _dispatch_prepared_scene_if_enabled(
    settings: "Settings",
    result: dict[str, object],
    rows: list["ClassificationRow"],
    *,
    device_id: str | None = None,
) -> str | None:
    from .preform_client import PreFormClient

    scene_id = result.get("scene_id")
    manifest = result.get("manifest")
    job_name = result.get("job_name")
    if not isinstance(scene_id, str) or not isinstance(job_name, str):
        return None
    if manifest is None:
        return None

    client = PreFormClient(settings.preform_server_url)
    try:
        return _dispatch_scene_if_enabled(
            client=client,
            settings=settings,
            scene_id=scene_id,
            manifest=manifest,
            rows=rows,
            job_name=job_name,
            device_id=device_id,
            force_dispatch=device_id is not None,
        )
    finally:
        client.close()
```

- [ ] **Step 3: Add a final accepted hold predicate**

Add this helper near `_should_hold_manifest()`:

```python
def _should_hold_accepted_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    now: datetime,
) -> bool:
    density_target = getattr(settings, "print_hold_density_target", 0.40)
    if density_target <= 0:
        return False
    if manifest.planning_status != "planned" or not manifest.import_groups:
        return False
    if manifest.estimated_density >= density_target:
        return False
    cutoff = _parse_cutoff_today(settings.print_hold_cutoff_local_time, now)
    return now < cutoff
```

- [ ] **Step 4: Add a helper that converts a reserved job to held**

Add this helper near `_update_reserved_print_job_from_result()`:

```python
def _update_reserved_print_job_as_held(
    connection,
    *,
    job_id: int,
    result: dict[str, object],
    settings: "Settings",
    cutoff_at: datetime,
    now: str,
) -> None:
    manifest = result["manifest"]
    screenshot_url = result.get("screenshot_url") or f"/api/print-queue/jobs/{job_id}/screenshot"
    connection.execute(
        """
        UPDATE print_jobs
        SET scene_id = ?,
            print_job_id = NULL,
            status = ?,
            preset = ?,
            preset_names_json = ?,
            compatibility_key = ?,
            case_ids = ?,
            manifest_json = ?,
            updated_at = ?,
            screenshot_url = ?,
            form_file_path = ?,
            printer_type = ?,
            printer_device_id = ?,
            printer_device_name = ?,
            resin = ?,
            layer_height_microns = ?,
            estimated_density = ?,
            density_target = ?,
            hold_cutoff_at = ?,
            hold_reason = ?,
            release_reason = NULL,
            released_by_operator = 0,
            validation_passed = ?,
            validation_errors_json = ?
        WHERE id = ?
        """,
        (
            result.get("scene_id"),
            HOLDING_STATUS,
            result["preset"],
            json.dumps(result.get("preset_names", [])),
            result.get("compatibility_key"),
            json.dumps(result["case_ids"]),
            json.dumps(result.get("manifest_json")) if result.get("manifest_json") is not None else None,
            now,
            screenshot_url,
            result.get("form_file_path"),
            result.get("printer_type"),
            result.get("printer_device_id"),
            result.get("printer_device_name"),
            result.get("resin"),
            result.get("layer_height_microns"),
            result.get("estimated_density"),
            settings.print_hold_density_target,
            cutoff_at.isoformat(),
            "below_density_target",
            (
                1 if result.get("validation_passed")
                else 0 if result.get("validation_passed") is False
                else None
            ),
            json.dumps(result.get("validation_errors", [])),
            job_id,
        ),
    )
```

- [ ] **Step 5: In selected-device dispatch, prepare without dispatching**

In `_send_ready_rows_to_device()`, change the call to `process_print_manifest()` to pass:

```python
                        dispatch_scene=False,
```

Immediately after `result is not None` and after failed import cases are marked, add:

```python
            accepted_manifest = result["manifest"]
            accepted_rows = _manifest_rows(accepted_manifest, rows_by_id)
            accepted_row_ids = [
                row.row_id
                for row in accepted_rows
                if row.row_id is not None
            ]

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
                        (HOLDING_STATUS, result["job_name"], created_print_job_id, now, row.row_id),
                    )
                groups.append(
                    _group_result(
                        manifest_id=manifest_id,
                        status="held",
                        row_ids=accepted_row_ids,
                        job_name=str(result["job_name"]),
                    )
                )
                continue

            result["print_job_id"] = _dispatch_prepared_scene_if_enabled(
                settings,
                result,
                accepted_rows,
                device_id=str(device["device_id"]),
            )
```

Then keep the existing `_update_reserved_print_job_from_result()` and accepted row history update path.

- [ ] **Step 6: In default dispatch, apply the same accepted hold check**

In `send_ready_rows_to_print()`, after `accepted_manifest = result["manifest"]` and `accepted_rows = _manifest_rows(...)`, add the same `_should_hold_accepted_manifest()` branch. For default dispatch, do not call `_dispatch_prepared_scene_if_enabled()` unless the existing dispatch mode requires it. Use:

```python
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
                            (HOLDING_STATUS, result["job_name"], created_print_job_id, now, row.row_id),
                        )
                    continue
```

- [ ] **Step 7: Add post-import hold regression for default dispatch**

Add this test to `tests/test_preform_handoff.py`:

```python
def test_import_quarantine_holds_accepted_manifest_when_density_drops_below_target(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "accepted-under-target.stl"
    broken_file = tmp_path / "broken-large.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 300.0, 120.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-ACCEPTED-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-accepted-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-BROKEN-LARGE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-broken-large",
                dimension_x_mm=300.0,
                dimension_y_mm=120.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "broken-large.stl")
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].case_ids == ["CASE-ACCEPTED-HOLD"]

    accepted_row = get_upload_row_by_id(settings, row_ids[0])
    broken_row = get_upload_row_by_id(settings, row_ids[1])
    assert accepted_row.handoff_stage == "Holding for More Cases"
    assert broken_row.status == "Needs Review"
```

- [ ] **Step 8: Add selected-device no-dispatch-before-hold regression**

Add this test to `tests/test_preform_handoff.py`:

```python
def test_selected_device_import_quarantine_holds_under_target_without_printer_dispatch(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "device-accepted-under-target.stl"
    broken_file = tmp_path / "device-broken-large.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 300.0, 120.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-DEVICE-ACCEPTED-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-accepted-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-DEVICE-BROKEN-LARGE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-broken-large",
                dimension_x_mm=300.0,
                dimension_y_mm=120.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "device-broken-large.stl")
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
    assert stub_client.print_jobs == []
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].estimated_density == 1200.0 / 69188.0
```

- [ ] **Step 9: Run post-PreForm hold tests**

Run:

```bash
python -m pytest tests/test_preform_handoff.py::test_import_quarantine_holds_accepted_manifest_when_density_drops_below_target tests/test_preform_handoff.py::test_selected_device_import_quarantine_holds_under_target_without_printer_dispatch -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "Hold accepted trays that fall below density after import"
```

Lore body:

```text
The planner density can be valid before PreForm import but fall below target when damaged cases are quarantined. Selected-device dispatch now prepares scenes without immediate printer submission, rechecks accepted density, and only dispatches after the final accepted tray clears the hold gate.

Constraint: Explicit selected-device dispatch must not send an under-target accepted tray before density is rechecked
Rejected: Sequencing alone | does not prevent density drops after PreForm case quarantine
Confidence: high
Scope-risk: broad
Tested: Post-import hold regressions for default and selected-device dispatch
```

---

### Task 6: Keep Held Replanning Lane-Scoped

**Files:**
- Modify: `app/services/print_queue_service.py:1481-1509`
- Modify: `tests/test_preform_handoff.py:1825-1995`

- [ ] **Step 1: Replace global held loading with lane-aware held loading**

Replace `_load_held_replan_rows(settings)` with:

```python
def _load_held_replan_rows(
    settings: "Settings",
    *,
    lane_keys: set[str] | None = None,
    device_id: str | None = None,
) -> tuple[list[int], list["ClassificationRow"]]:
    from contextlib import closing

    from ..database import _load_rows_by_ids, connect, list_print_jobs
    from ..schemas import BuildManifest

    held_job_ids: list[int] = []
    held_row_ids: list[int] = []
    for job in list_print_jobs(settings):
        if job.status != HOLDING_STATUS or job.id is None or job.manifest_json is None:
            continue
        try:
            manifest = BuildManifest.model_validate(job.manifest_json)
        except Exception:
            continue
        job_lane_key = _build_lane_key_from_manifest(
            manifest,
            device_id=job.printer_device_id if job.printer_device_id else device_id,
        )
        if lane_keys is not None and job_lane_key not in lane_keys:
            continue
        held_job_ids.append(job.id)
        for group in job.manifest_json.get("import_groups", []):
            if not isinstance(group, dict):
                continue
            for file_spec in group.get("files", []):
                if isinstance(file_spec, dict) and file_spec.get("row_id") is not None:
                    held_row_ids.append(int(file_spec["row_id"]))

    if not held_row_ids:
        return held_job_ids, []

    with closing(connect(settings)) as connection:
        held_rows = _load_rows_by_ids(connection, sorted(set(held_row_ids)))

    return held_job_ids, [
        row.model_copy(update={"status": "Ready"})
        for row in held_rows
        if row.row_id is not None
    ]
```

- [ ] **Step 2: Load held rows after candidate lane keys are known**

In both dispatch paths:

1. Plan selected ready rows without held rows.
2. Compute candidate `lane_keys`.
3. Acquire those lane locks.
4. Load held rows filtered by those `lane_keys`.
5. Replan `held_replan_rows + selected rows`.
6. Delete only the matching held job IDs inside the same DB transaction.

For selected-device dispatch, use:

```python
    initial_planning_rows = _selected_model_rows(prevalidated_rows, device)
    initial_manifests = plan_build_manifests(
        initial_planning_rows,
        max_layout_density=settings.print_max_layout_density,
    )
    lane_keys = set(_build_lane_keys_from_manifests(initial_manifests, device_id=str(device["device_id"])))
    with _build_lane_locks(settings, sorted(lane_keys), operation="send_to_print"):
        held_job_ids, held_replan_rows = _load_held_replan_rows(
            settings,
            lane_keys=lane_keys,
            device_id=str(device["device_id"]),
        )
        ...
```

For default dispatch, use:

```python
    initial_manifests = plan_build_manifests(
        ready_rows,
        max_layout_density=settings.print_max_layout_density,
    )
    lane_keys = set(_build_lane_keys_from_manifests(initial_manifests))
    with _build_lane_locks(settings, sorted(lane_keys), operation="send_to_print"):
        held_job_ids, held_replan_rows = _load_held_replan_rows(settings, lane_keys=lane_keys)
        ...
```

- [ ] **Step 3: Strengthen held-replan tests**

Ensure `test_selected_device_new_compatible_rows_replan_with_existing_held_build` includes:

```python
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].printer_device_name == "Lab Printer"
    assert jobs[0].status == "Queued"
    assert jobs[0].hold_reason is None

    held_row = get_upload_row_by_id(settings, first_ids[0])
    filler_row = get_upload_row_by_id(settings, second_ids[0])
    assert held_row is not None
    assert filler_row is not None
    assert held_row.linked_print_job_id == jobs[0].id
    assert filler_row.linked_print_job_id == jobs[0].id
    assert held_row.queue_section == "history"
    assert filler_row.queue_section == "history"
```

Add this test:

```python
def test_different_device_does_not_merge_existing_selected_device_hold(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "device-a-held.stl"
    device_b_file = tmp_path / "device-b-case.stl"
    for file_path in (held_file, device_b_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(held_file), 40.0, 30.0)
    register_test_dims(str(device_b_file), 40.0, 30.0)

    first_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-DEVICE-A-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-a-held",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )
    second_ids = _seed_rows(
        settings,
        [
            _row_payload(
                device_b_file,
                case_id="CASE-DEVICE-B",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-b",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-a", "name": "Printer A", "model": "Form 4BL", "status": "ready"},
        {"id": "form-4bl-b", "name": "Printer B", "model": "Form 4BL", "status": "ready"},
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": first_ids, "device_id": "form-4bl-a"},
        )
        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": second_ids, "device_id": "form-4bl-b"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 2
    assert {job.printer_device_id for job in jobs} == {"form-4bl-a", "form-4bl-b"}
    assert all(job.status == "Holding for More Cases" for job in jobs)
```

- [ ] **Step 4: Run held replan tests**

Run:

```bash
python -m pytest tests/test_preform_handoff.py::test_new_compatible_rows_replan_with_existing_held_build tests/test_preform_handoff.py::test_selected_device_new_compatible_rows_replan_with_existing_held_build tests/test_preform_handoff.py::test_different_device_does_not_merge_existing_selected_device_hold -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py
git commit -m "Scope held-build replanning to compatible lanes"
```

Lore body:

```text
Held builds should absorb later compatible rows, but only inside the same tray lane. Held-row loading now filters by lane so different selected devices or incompatible materials do not merge while same-lane requests replace the held job atomically.

Constraint: Selected physical devices form separate lanes
Rejected: Load all held jobs globally | can merge incompatible printer targets
Confidence: high
Scope-risk: moderate
Tested: Default, selected-device, and different-device held replan tests
```

---

### Task 7: Verification And Packaged-App Proof

**Files:**
- Read: `.codex/skills/formflow-release/SKILL.md`
- Read: `dist/data/formflow.db`
- Read: `dist/output/`
- Optional modify: `.codex/skills/formflow-release/SKILL.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
python -m pytest tests/test_print_queue.py tests/test_preform_handoff.py tests/test_upload_classification.py -q
```

Expected: PASS.

- [ ] **Step 2: Run release-related tests**

Run:

```bash
python -m pytest tests/test_exe_packaging.py tests/test_health_endpoints.py tests/test_tray_runtime.py -q
```

Expected: PASS.

- [ ] **Step 3: Build the Windows EXE**

Run:

```bash
python scripts/builders/build_windows_exe.py --version 0.1.0
```

Expected: `dist/FormFlow_v0.1.0.exe` is rebuilt.

- [ ] **Step 4: Smoke the EXE**

Use `.codex/skills/formflow-release/SKILL.md`.

Expected:

- packaged app starts from `dist`
- `/health` returns HTTP 200
- app uses `dist/data/formflow.db`
- output goes under `dist/output/`

- [ ] **Step 5: Live PreFormServer verification**

Run a live scenario with PreFormServer ready and a dataset that includes:

- compatible rows for one Form 4BL Precision Model 100um lane
- a damaged STL that PreForm rejects
- later compatible rows that should merge into a held build
- a selected-device send path

Expected evidence:

- at most one `Holding for More Cases` job per lane
- no queued job below `print_hold_density_target` unless released by cutoff/operator
- selected-device under-target accepted trays have no PreForm print submission
- held rows replan with later same-lane rows
- different selected devices do not merge held jobs

- [ ] **Step 6: Inspect packaged SQLite proof**

Run:

```bash
python - <<'PY'
import json, sqlite3
conn = sqlite3.connect("dist/data/formflow.db")
conn.row_factory = sqlite3.Row
jobs = list(conn.execute("""
    SELECT job_name, status, estimated_density, density_target, hold_reason,
           printer_device_id, printer_type, resin, layer_height_microns, manifest_json
    FROM print_jobs
    ORDER BY job_name
"""))
for row in jobs:
    manifest = json.loads(row["manifest_json"]) if row["manifest_json"] else {}
    file_sum = sum(
        float(file_spec.get("xy_footprint_estimate") or 0.0)
        for group in manifest.get("import_groups", [])
        for file_spec in group.get("files", [])
    )
    budget = float(manifest.get("printer_xy_budget") or 0.0)
    recomputed = file_sum / budget if budget else 0.0
    print(
        row["job_name"],
        row["status"],
        round(float(row["estimated_density"] or 0.0), 6),
        round(recomputed, 6),
        row["hold_reason"],
        row["printer_device_id"],
        row["printer_type"],
        row["resin"],
        row["layer_height_microns"],
    )
conn.close()
PY
```

Expected:

- persisted density matches recomputed density for every job
- no `Queued` job prints below target unless it has a release reason
- there is no duplicate held job for the same lane

- [ ] **Step 7: Commit release checklist update only if changed**

If `.codex/skills/formflow-release/SKILL.md` changes:

```bash
git add .codex/skills/formflow-release/SKILL.md
git commit -m "Require lane and density proof in FormFlow release"
```

Lore body:

```text
The release proof now checks that compatible build lanes serialize, held builds remain unique per lane, and accepted manifest density is revalidated after PreForm rejects damaged cases.

Confidence: medium
Scope-risk: narrow
Tested: Release checklist review
```

---

## Self-Review

- Spec coverage: This plan covers lane-based concurrency, duplicate held-build prevention, selected-device lane separation, post-PreForm density recheck, selected-device no-dispatch-before-hold, held replan scoping, and packaged proof.
- Deferred-wording scan: No task uses vague deferred wording; each implementation task includes concrete files, code snippets, tests, commands, and expected outcomes.
- Type consistency: Planned helpers use existing `BuildManifest`, `ClassificationRow`, `Settings`, `PrintJob`, `DeviceDispatchValidationError`, `process_print_manifest`, and SQLite patterns already present in the repo.
- Risk note: Task 5 is the highest-risk change because it alters when selected-device dispatch calls PreForm `/print/`. Keep its tests focused and run live PreForm verification before claiming release readiness.
