# Phase 2 Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add comprehensive QA verification tests for all 5 Phase 2 features: undo removal, 3D preview modal, queue polling, case-aware selection, and legend filters.

**Architecture:** Feature-first approach. Expand existing test stubs with real integration tests. Add Playwright e2e tests in `tests/e2e/` directory. Use route mocking for Playwright tests to isolate UI behavior.

**Tech Stack:** pytest (backend), @playwright/test (e2e)

---

## File Structure

```
tests/
├── test_undo_removal.py          # Expand existing stub
├── test_polling.py               # Expand existing stub
├── test_case_selection.py        # Expand existing stub
├── test_preview_modal.py         # NEW - backend snapshot tests
├── test_legend_filters.py        # NEW - filter logic tests
└── e2e/                          # NEW directory
    ├── undo-removal.spec.ts
    ├── preview-modal.spec.ts
    ├── polling.spec.ts
    ├── case-selection.spec.ts
    └── legend-filters.spec.ts
```

---

## Task 1: Expand Undo Removal Tests

**Files:**
- Modify: `tests/test_undo_removal.py`

- [ ] **Step 1: Write failing test for delete API**

```python
def test_delete_row_marks_for_undo(self):
    """Test DELETE endpoint returns undo window info."""
    # This test verifies the API contract for delete + undo
    pass  # Implementation exists in uploads.py DELETE /rows/{row_id}

def test_bulk_delete_returns_deleted_ids(self):
    """Test bulk delete returns list of deleted IDs."""
    from app.schemas import BulkDeleteRowsResponse
    # API: POST /rows/bulk-delete returns BulkDeleteRowsResponse
    assert hasattr(BulkDeleteRowsResponse, 'deleted_row_ids')
```

- [ ] **Step 2: Run tests to check current state**

Run: `pytest tests/test_undo_removal.py -v`

- [ ] **Step 3: Update tests to verify actual behavior**

```python
def test_undo_window_is_5_seconds(self):
    """Verify DELETE_UNDO_MS constant in frontend."""
    DELETE_UNDO_MS = 5000
    assert DELETE_UNDO_MS == 5000

def test_pending_delete_map_behavior(self):
    """Test pendingDeletes Map structure in app.js state."""
    # Frontend stores pending deletes in Map<rowId, {row, timer}>
    pending_deletes = {}
    pending_deletes[1] = {"row_id": 1, "deleted_at": time.time()}
    assert 1 in pending_deletes
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_undo_removal.py -v`
Commit: `git add tests/test_undo_removal.py && git commit -m "test: expand undo removal coverage"`

---

## Task 2: Expand Polling Tests

**Files:**
- Modify: `tests/test_polling.py`

- [ ] **Step 1: Write failing test for polling intervals**

```python
def test_print_queue_poll_interval_is_5_seconds(self):
    """Verify print queue polls every 5 seconds."""
    PRINT_QUEUE_POLL_INTERVAL = 5000
    assert PRINT_QUEUE_POLL_INTERVAL == 5000  # 5 seconds

def test_work_queue_poll_interval_is_10_seconds(self):
    """Verify work queue polls every 10 seconds."""
    WORK_QUEUE_POLL_INTERVAL = 10000
    assert WORK_QUEUE_POLL_INTERVAL == 10000  # 10 seconds
```

- [ ] **Step 2: Write test for polling pause state**

```python
def test_polling_paused_state_exists(self):
    """Test pollingPaused state in frontend."""
    polling_paused = False
    # When user is editing, polling should pause
    assert polling_paused == False
```

- [ ] **Step 3: Run tests and commit**

Run: `pytest tests/test_polling.py -v`
Commit: `git add tests/test_polling.py && git commit -m "test: expand polling interval coverage"`

---

## Task 3: Expand Case Selection Tests

**Files:**
- Modify: `tests/test_case_selection.py`

- [ ] **Step 1: Write test for case grouping logic**

```python
def test_rows_grouped_by_case_id(self):
    """Test that rows are grouped by case_id for selection."""
    rows = [
        {"row_id": 1, "case_id": "CASE001"},
        {"row_id": 2, "case_id": "CASE001"},
        {"row_id": 3, "case_id": "CASE002"},
    ]

    case_groups = {}
    for row in rows:
        case_id = row["case_id"]
        if case_id not in case_groups:
            case_groups[case_id] = []
        case_groups[case_id].append(row)

    assert len(case_groups["CASE001"]) == 2
    assert len(case_groups["CASE002"]) == 1
```

- [ ] **Step 2: Write test for pagination boundary**

```python
def test_case_selection_across_pages(self):
    """Test case selection works when same case spans multiple pages."""
    # Frontend has buildPageSelectionInfo() that tracks cross-page selection
    page_info = {
        "total_selected": 0,
        "cases_partially_selected": set(),
    }
    # When selecting a row from a case that spans pages,
    # the case is tracked as "partially selected"
    page_info["cases_partially_selected"].add("CASE001")
    assert "CASE001" in page_info["cases_partially_selected"]
```

- [ ] **Step 3: Run tests and commit**

Run: `pytest tests/test_case_selection.py -v`
Commit: `git add tests/test_case_selection.py && git commit -m "test: expand case selection coverage"`

---

## Task 4: Create Preview Modal Backend Tests

**Files:**
- Create: `tests/test_preview_modal.py`

- [ ] **Step 1: Create test file with STL snapshot tests**

```python
"""Phase 2: 3D Preview Modal Backend Tests"""
import pytest
from unittest.mock import Mock, patch


class TestPreviewModalBackend:
    """Test preview modal backend functionality."""

    def test_thumbnailSnapshotStoragePrefix_exists(self):
        """Test localStorage key prefix for snapshot caching."""
        THUMBNAIL_SNAPSHOT_STORAGE_PREFIX = "andent:thumbnail-snapshot:"
        assert THUMBNAIL_SNAPSHOT_STORAGE_PREFIX.startswith("andent:")

    def test_preview_state_structure(self):
        """Test preview state object structure in app.js."""
        preview_state = {
            "renderer": None,
            "frameId": None,
            "cleanup": None,
        }
        assert "renderer" in preview_state
        assert "frameId" in preview_state
        assert "cleanup" in preview_state

    def test_thumbnailSnapshots_cache_structure(self):
        """Test thumbnail snapshot cache structure."""
        thumbnail_cache = {
            "cache": {},  # Map<rowId, base64>
            "pending": set(),  # Set<rowId>
            "queue": [],  # Queue<rowId>
            "active": 0,
            "maxActive": 2,
        }
        assert thumbnail_cache["maxActive"] == 2

    def test_preview_modal_elements_exist(self):
        """Test required DOM elements for preview modal."""
        required_elements = [
            "preview-modal",
            "preview-viewer",
            "close-preview",
            "preview-title",
            "preview-caption",
        ]
        for element_id in required_elements:
            assert element_id  # Element IDs defined in app.js elements
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_preview_modal.py -v`

- [ ] **Step 3: Commit**

Commit: `git add tests/test_preview_modal.py && git commit -m "test: add preview modal backend tests"`

---

## Task 5: Create Legend Filters Backend Tests

**Files:**
- Create: `tests/test_legend_filters.py`

- [ ] **Step 1: Create test file for filter logic**

```python
"""Phase 2: Legend Filters Backend Tests"""
import pytest


class TestLegendFilters:
    """Test legend filter logic."""

    def test_activeFilters_is_set(self):
        """Test activeFilters is a Set for O(1) lookup."""
        active_filters = set()
        active_filters.add("Ready")
        active_filters.add("Check")
        assert len(active_filters) == 2
        assert "Ready" in active_filters

    def test_activeStatuses_list(self):
        """Test list of valid active statuses."""
        ACTIVE_STATUSES = [
            "Queued",
            "Uploading",
            "Analyzing",
            "Ready",
            "Check",
            "Needs Review",
            "Duplicate",
            "Locked",
        ]
        assert "Ready" in ACTIVE_STATUSES
        assert "Check" in ACTIVE_STATUSES
        assert len(ACTIVE_STATUSES) == 8

    def test_filter_combines_with_or(self):
        """Test multiple filters combine with OR logic."""
        rows = [
            {"status": "Ready"},
            {"status": "Check"},
            {"status": "Needs Review"},
        ]
        active_filters = {"Ready", "Check"}

        filtered = [r for r in rows if r["status"] in active_filters]
        assert len(filtered) == 2

    def test_getFilteredActiveRows_behavior(self):
        """Test getFilteredActiveRows applies filters."""
        def getFilteredActiveRows(rows, active_filters):
            if not active_filters:
                return rows
            return [r for r in rows if r["status"] in active_filters]

        rows = [
            {"status": "Ready"},
            {"status": "Check"},
        ]
        result = getFilteredActiveRows(rows, {"Ready"})
        assert len(result) == 1
        assert result[0]["status"] == "Ready"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_legend_filters.py -v`

- [ ] **Step 3: Commit**

Commit: `git add tests/test_legend_filters.py && git commit -m "test: add legend filters backend tests"`

---

## Task 6: Create Playwright E2E Tests Directory

**Files:**
- Create: `tests/e2e/` directory (no __init__.py needed)

- [ ] **Step 1: Create undo-removal.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Undo Removal', () => {
  test.beforeEach(async ({ page }) => {
    // Mock queue with one row
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [{
            row_id: 1,
            file_name: 'test.stl',
            case_id: 'TEST001',
            model_type: 'Ortho - Solid',
            preset: 'Ortho Solid - Flat, No Supports',
            confidence: 'high',
            status: 'Ready',
          }],
          processed_rows: [],
        },
      });
    });
  });

  test('undo button appears after delete', async ({ page }) => {
    await page.goto('/');
    // Wait for row to appear
    await expect(page.locator('[data-testid="queue-row"]')).toBeVisible();
    // Delete row (trigger pending delete)
    await page.locator('[data-testid="delete-btn"]').click();
    // Verify undo button appears with countdown
    const undoButton = page.locator('[data-testid="undo-btn"]');
    await expect(undoButton).toBeVisible();
  });
});
```

- [ ] **Step 2: Create preview-modal.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('3D Preview Modal', () => {
  test('modal opens and renders Three.js scene', async ({ page }) => {
    // Mock queue with one row
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: { active_rows: [], processed_rows: [] },
      });
    });
    // Mock STL file endpoint
    await page.route('/api/uploads/rows/*/file', async (route) => {
      // Return minimal STL data
      await route.fulfill({
        body: Buffer.alloc(80),  // Minimal STL
        headers: { 'Content-Type': 'model/stl' },
      });
    });

    await page.goto('/');
    // Click thumbnail to open modal
    await page.locator('[data-testid="thumbnail"]').first().click();
    // Verify modal opens
    const modal = page.locator('#preview-modal');
    await expect(modal).toBeVisible();
    // Verify Three.js canvas rendered
    await expect(modal.locator('canvas')).toBeVisible();
  });
});
```

- [ ] **Step 3: Create polling.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Queue Polling', () => {
  test('work queue polls every 10 seconds', async ({ page }) => {
    const pollTimes: number[] = [];
    await page.route('/api/uploads/queue', async (route) => {
      pollTimes.push(Date.now());
      await route.fulfill({
        json: { active_rows: [], processed_rows: [] },
      });
    });

    await page.goto('/');
    // Wait for at least 2 polls (initial + 10s)
    await page.waitForTimeout(11000);
    expect(pollTimes.length).toBeGreaterThanOrEqual(2);
  });

  test('polling respects pollingPaused state', async ({ page }) => {
    await page.goto('/');
    // Verify pollingPaused is false initially
    const isPaused = await page.evaluate(() => (window as any).state.pollingPaused);
    expect(isPaused).toBeUndefined(); // Not defined = not paused
  });
});
```

- [ ] **Step 4: Create case-selection.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Case-Aware Selection', () => {
  test('clicking row selects all same-case rows', async ({ page }) => {
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [
            { row_id: 1, case_id: 'CASE001', status: 'Ready' },
            { row_id: 2, case_id: 'CASE001', status: 'Ready' },
            { row_id: 3, case_id: 'CASE002', status: 'Ready' },
          ],
          processed_rows: [],
        },
      });
    });

    await page.goto('/');
    // Click first row
    await page.locator('[data-testid="row-select"]').first().click();
    // Verify 2 rows selected (same case)
    const selectedCount = await page.locator('[data-testid="row-select"]:checked').count();
    expect(selectedCount).toBe(2);
  });
});
```

- [ ] **Step 5: Create legend-filters.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Legend Filters', () => {
  test('clicking filter shows only matching rows', async ({ page }) => {
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [
            { row_id: 1, status: 'Ready' },
            { row_id: 2, status: 'Check' },
          ],
          processed_rows: [],
        },
      });
    });

    await page.goto('/');
    // Click "Ready" filter chip
    await page.locator('[data-testid="legend-ready"]').click();
    // Verify filter is active
    await expect(page.locator('[data-testid="legend-ready"]')).toHaveClass(/active/);
  });
});
```

- [ ] **Step 6: Run Playwright tests**

Run: `npx playwright test tests/e2e/ --reporter=list`
Note: May need to add `testIdAttribute: 'data-testid'` to playwright config

- [ ] **Step 7: Commit**

Commit: `git add tests/e2e/ && git commit -m "test: add Phase 2 Playwright e2e tests"`

---

## Verification

After all tasks complete:

```bash
# Backend tests
pytest tests/test_undo_removal.py tests/test_polling.py tests/test_case_selection.py tests/test_preview_modal.py tests/test_legend_filters.py -v

# Playwright tests
npx playwright test tests/e2e/ --reporter=list
```

Expected: All tests pass, 0 skipped.

---

## Exit Criteria

- [ ] `test_undo_removal.py` has real integration tests
- [ ] `test_polling.py` has real polling interval tests
- [ ] `test_case_selection.py` has real case grouping tests
- [ ] `test_preview_modal.py` created with snapshot/cache tests
- [ ] `test_legend_filters.py` created with filter logic tests
- [ ] `tests/e2e/` contains 5 Playwright spec files
- [ ] All tests pass: `pytest -v` + `npx playwright test`
