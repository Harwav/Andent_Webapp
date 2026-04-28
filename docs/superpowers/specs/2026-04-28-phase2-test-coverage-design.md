# Phase 2 Test Coverage Design

**Date:** 2026-04-28
**Status:** Approved
**Scope:** QA verification tests for all Phase 2 Enhanced Queue Features

---

## Context

Phase 2 Enhanced Queue Features are fully implemented in the codebase but lack comprehensive test coverage. The roadmap documents these as "partially implemented" due to uneven test coverage. This spec defines test coverage for QA verification purposes.

---

## Features Under Test

| Feature | Description | Priority |
|---------|-------------|----------|
| Undo removal | 5-second window to undo row deletions | P1 |
| 3D preview modal | Three.js STL viewer in modal | P1 |
| Queue polling | Auto-refresh every 5-10s | P1 |
| Case-aware selection | Auto-select all rows sharing case_id | P1 |
| Legend filters | Clickable status filters | P1 |

---

## Test Strategy

**Approach:** Feature-first, complete end-to-end for each feature before moving to the next.

**Types:**
- Backend (pytest): Unit/integration tests for API logic and services
- Playwright (e2e): UI interaction tests for QA verification

**Classification:** QA verification only (not release gates)

---

## Backend Tests

### Undo Removal (`tests/test_undo_removal.py`)

**Expand existing stub to cover:**

| Test | Description |
|------|-------------|
| `test_delete_pending_timeout` | Verify deleted rows expire after 5s |
| `test_undo_restores_row` | DELETE + undo restores original state |
| `test_undo_clears_pending` | Undo removes from pendingDeletes map |
| `test_bulk_delete_undo` | Bulk delete + undo restores all rows |

**Fixtures:** Shared `test_app` fixture, `sample_upload_row`

### 3D Preview Modal

**New file:** `tests/test_preview_modal.py`

| Test | Description |
|------|-------------|
| `test_stl_snapshot_generation` | STL renders to PNG snapshot |
| `test_snapshot_cached` | Subsequent renders use cache |
| `test_modal_loads_stl` | Preview endpoint serves STL data |

**Dependencies:** `tests/fixtures/stl/` with sample `.stl` files

### Queue Polling (`tests/test_polling.py`)

**Expand existing to cover:**

| Test | Description |
|------|-------------|
| `test_polling_interval` | Verify 10s work queue, 5s print queue intervals |
| `test_polling_pause_resume` | Polling respects pollingPaused flag |
| `test_polling_error_handling` | Graceful handling on API failure |

### Case-Aware Selection (`tests/test_case_selection.py`)

**Expand existing to cover:**

| Test | Description |
|------|-------------|
| `test_case_group_identified` | Rows with same case_id grouped |
| `test_select_one_selects_all` | Selecting any row in group selects all |
| `test_pagination_boundary` | Cross-page selection handled correctly |

### Legend Filters

**New file:** `tests/test_legend_filters.py`

| Test | Description |
|------|-------------|
| `test_filter_by_status` | Filter returns only matching status |
| `test_multiple_filters` | Multiple active filters combine with OR |
| `test_filter_persists` | Filter state survives navigation |

---

## Playwright Tests

**New directory:** `tests/e2e/`

### Undo Removal (`tests/e2e/undo-removal.spec.ts`)

```
1. Upload a file and wait for classification
2. Delete the row
3. Verify undo button appears with countdown
4. Click undo
5. Verify row restored to table
6. Wait 6s, delete, verify undo button gone
```

### 3D Preview Modal (`tests/e2e/preview-modal.spec.ts`)

```
1. Upload an STL file
2. Click thumbnail
3. Verify modal opens
4. Verify Three.js renders model
5. Verify rotation/zoom controls work
6. Close modal
7. Click again - verify cache used
```

### Queue Polling (`tests/e2e/polling.spec.ts`)

```
1. Open queue tab
2. Verify initial poll occurs
3. Make API change in background
4. Wait 15s, verify UI updated
5. Pause polling, make change, verify no update
6. Resume polling, verify catch-up
```

### Case-Aware Selection (`tests/e2e/case-selection.spec.ts`)

```
1. Upload multiple files with same case_id
2. Click first row
3. Verify all same-case rows selected
4. Click different case row
5. Verify previous selection cleared
6. Verify count badge shows correct number
```

### Legend Filters (`tests/e2e/legend-filters.spec.ts`)

```
1. Verify legend renders with all status chips
2. Click "Ready" filter
3. Verify only Ready rows visible
4. Click "Check" filter
5. Verify Ready + Check rows visible
6. Click active filter to deactivate
7. Verify filter removed from active set
```

---

## Test Data

**Fixtures directory:** `tests/fixtures/`

| Fixture | Purpose |
|---------|---------|
| `fixtures/stl/ortho_upper.stl` | STL for preview tests |
| `fixtures/stl/die_tooth.stl` | STL for selection tests |
| `fixtures/fixtures.py` | Shared pytest fixtures |

---

## Verification

After implementation:

1. Run `pytest tests/test_undo_removal.py tests/test_polling.py tests/test_case_selection.py -v`
2. Run `pytest tests/test_preview_modal.py tests/test_legend_filters.py -v`
3. Run `npx playwright test tests/e2e/ --reporter=list`
4. Verify all tests pass with 0 skipped

---

## Exit Criteria

- All 5 Phase 2 features have backend (pytest) test coverage
- All 5 Phase 2 features have Playwright e2e test coverage
- Tests run successfully against live application
- Test output shows green across all Phase 2 feature tests
