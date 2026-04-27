# Preset Printer Hold Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the user-visible Phase 1 preset, printer-group, and holding-policy workflow on top of the approved design.

**Status:** Complete and verified 2026-04-27.

**Architecture:** Keep the backend source of truth in existing FastAPI schemas, SQLite helpers, and `print_queue_service`. The browser remains vanilla JS and posts row-level operator choices to the existing upload-row update endpoints; planner and hold logic consume those persisted choices.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, vanilla JavaScript, Playwright release-gate tests where browser behavior changes.

---

## File Structure

- Modify `app/schemas.py` for upload-row update request fields.
- Modify `app/database.py` for durable printer-group updates and events.
- Modify `app/routers/uploads.py` to pass printer values through row update endpoints.
- Modify `app/static/index.html` and `app/static/app.js` for Work Queue printer controls.
- Modify `tests/test_durable_overrides.py`, `tests/test_upload_classification.py`, and `tests/test_frontend_static.py` for focused contract coverage.
- Keep existing `app/services/build_planning.py`, `app/services/preset_catalog.py`, and `app/services/print_queue_service.py` behavior unless tests expose a contract gap.

### Task 1: Persist Operator Printer Group Edits

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/database.py`
- Modify: `app/routers/uploads.py`
- Test: `tests/test_durable_overrides.py`

- [x] **Step 1: Write the failing test**

```python
def test_manual_printer_group_update_persists_for_row(tmp_path):
    from app.database import get_upload_row_by_id, init_db, persist_upload_session, update_upload_row

    settings = _test_settings(tmp_path)
    init_db(settings)
    [row] = persist_upload_session(settings, "session-printer", [_stored_row()])

    updated = update_upload_row(
        settings,
        row.row_id,
        model_type=row.model_type,
        preset=row.preset,
        printer="Form 4B",
    )

    assert updated.printer == "Form 4B"
    assert get_upload_row_by_id(settings, row.row_id).printer == "Form 4B"
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_durable_overrides.py::test_manual_printer_group_update_persists_for_row -q`

Expected: FAIL because `update_upload_row()` does not accept `printer`.

- [x] **Step 3: Write minimal implementation**

Add `printer: str | None = None` to `UpdateClassificationRowRequest` and `BulkUpdateClassificationRowsRequest`. Thread `payload.printer` through the upload router. Update `update_upload_row()` and `bulk_update_upload_rows()` to write `printer = ?` without changing status derivation.

- [x] **Step 4: Run test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_durable_overrides.py::test_manual_printer_group_update_persists_for_row -q`

Expected: PASS.

### Task 2: Expose Printer Group Selection In Work Queue

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Test: `tests/test_frontend_static.py`

- [x] **Step 1: Write the failing test**

```python
def test_active_work_queue_exposes_printer_group_selector():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "Printer" in index_html
    assert "PRINTER_OPTIONS" in app_js
    assert "createPrinterSelect" in app_js
    assert 'printer: row.printer || null' in app_js
    assert 'data-testid = "printer-select"' in app_js
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_active_work_queue_exposes_printer_group_selector -q`

Expected: FAIL because there is no active queue printer selector.

- [x] **Step 3: Write minimal implementation**

Add `const PRINTER_OPTIONS = ["Form 4BL", "Form 4B"];`. Add a `Printer` column to the active and in-progress tables. Add `createPrinterSelect(row)` using the same lock/persist pattern as model and preset selects, and include `printer` in `persistRow()`.

- [x] **Step 4: Run test to verify it passes**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_active_work_queue_exposes_printer_group_selector -q`

Expected: PASS.

### Task 3: Support Bulk Printer Group Edits

**Files:**
- Modify: `app/database.py`
- Modify: `app/routers/uploads.py`
- Modify: `app/static/app.js`
- Test: `tests/test_durable_overrides.py`
- Test: `tests/release_gate/bulk-actions.spec.ts`

- [x] **Step 1: Write the failing backend test**

```python
def test_bulk_printer_group_update_persists_for_rows(tmp_path):
    from app.database import bulk_update_upload_rows, init_db, persist_upload_session

    settings = _test_settings(tmp_path)
    init_db(settings)
    rows = persist_upload_session(settings, "session-printer-bulk", [_stored_row("a.stl"), _stored_row("b.stl")])

    updated = bulk_update_upload_rows(
        settings,
        [row.row_id for row in rows],
        model_type=None,
        preset=None,
        printer="Form 4B",
    )

    assert [row.printer for row in updated] == ["Form 4B", "Form 4B"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_durable_overrides.py::test_bulk_printer_group_update_persists_for_rows -q`

Expected: FAIL because `bulk_update_upload_rows()` does not accept `printer`.

- [x] **Step 3: Write minimal implementation**

Add the optional `printer` argument to `bulk_update_upload_rows()`, persist it in the update statement, record it in the event metadata, and render a Work Queue bulk printer selector that posts `{ row_ids, printer }`.

- [x] **Step 4: Run focused tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_durable_overrides.py tests/test_frontend_static.py -q`

Expected: PASS.

### Task 4: Close Holding UI Metadata Gaps

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_frontend_static.py`

- [x] **Step 1: Write the failing test**

```python
def test_print_queue_displays_holding_density_cutoff_and_release():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "formatDensity" in app_js
    assert "hold_cutoff_at" in app_js
    assert "density_target" in app_js
    assert "Release now" in app_js
    assert "/release-now" in app_js
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_print_queue_displays_holding_density_cutoff_and_release -q`

Expected: FAIL only on missing metadata helpers or labels.

- [x] **Step 3: Write minimal implementation**

Render estimated density, target density, cutoff, hold reason, and release reason in expanded print-job details. Keep the existing `release-now` endpoint and button path.

- [x] **Step 4: Run focused tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py tests/test_print_queue.py tests/test_print_queue_polling.py -q`

Expected: PASS.

### Task 5: Verify End-To-End Contract

**Files:**
- Modify only files touched by failing tests.
- Test: existing focused backend and frontend contract tests.

- [x] **Step 1: Run preset/planner/backend tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preset_catalog.py tests/test_build_planning.py tests/test_batching.py tests/test_print_queue.py tests/test_print_queue_polling.py tests/test_upload_classification.py -q`

Expected: PASS.

- [x] **Step 2: Run frontend static contract tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py -q`

Expected: PASS.

- [x] **Step 3: Update spec status**

## Verification Evidence

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q` -> 250 passed, 5 existing STL warnings.
- `npx tsc --noEmit` -> passed.
- `ANDENT_PLAYWRIGHT_PORT=53123 npx playwright test tests/release_gate/bulk-actions.spec.ts --project=chromium` -> 2 passed.

Change `docs/superpowers/specs/2026-04-24-preset-printer-hold-policy-design.md` status from implementation-plan pending to implementation in progress or complete, depending on the completed task set and verification evidence.
