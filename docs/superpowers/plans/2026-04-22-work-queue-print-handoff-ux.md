# Work Queue Print Handoff UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape the queue experience so the app keeps operators on one `Work Queue` page with `File Analysis` and read-only `In Progress` sections, adds file-level `History` traceability, and converts `Print Queue` into a job-level table with screenshot preview behavior.

**Architecture:** Extend upload-row persistence with lightweight handoff metadata so the backend can distinguish actionable rows, in-progress rows, and historical rows without inventing a separate workflow store. Then update the queue snapshot, print queue rendering, and file-history linking so the frontend can express the approved UX while keeping the existing FastAPI + vanilla-JS structure.

**Tech Stack:** FastAPI, SQLite, Pydantic, pytest, vanilla JS, existing PreFormServer handoff service

---

## File Structure

### Existing files to modify

- `app/database.py`
  - Add upload-row workflow metadata columns and queue/history row mapping.
- `app/schemas.py`
  - Extend `ClassificationRow` with the metadata needed by `Work Queue` and `History`.
- `app/services/print_queue_service.py`
  - Persist in-progress states during handoff and attach job-link metadata on success.
- `app/routers/uploads.py`
  - Keep using the existing queue endpoint, but return richer row snapshots after send.
- `app/static/index.html`
  - Replace `Active`/`Processed` labels and panels with `Work Queue`, `History`, and a table-based `Print Queue`.
- `app/static/app.js`
  - Render `File Analysis` + `In Progress`, keep users on `Work Queue`, show mixed-result messages, support brief `Queued`, and add `History` -> `Print Queue` linking.
- `app/static/styles.css`
  - Style the new queue sections, read-only `In Progress`, history link affordances, and print queue table.
- `tests/test_frontend_static.py`
  - Lock the new static frontend contract.
- `tests/test_preform_handoff.py`
  - Lock backend workflow metadata and row movement through handoff.
- `tests/test_print_queue_polling.py`
  - Lock screenshot placeholder behavior and print queue API expectations.

## Task 1: Add failing tests for row workflow metadata

**Files:**
- Modify: `tests/test_preform_handoff.py`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Write the failing backend workflow test**

```python
def test_send_to_print_marks_rows_with_history_job_link_metadata(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "ortho-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE901",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-901",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "Submitted"
    assert row["queue_section"] == "history"
    assert row["handoff_stage"] == "Queued"
    assert row["linked_job_name"] is not None
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_handoff.py::test_send_to_print_marks_rows_with_history_job_link_metadata -q`

Expected: FAIL because `ClassificationRow` and upload-row persistence do not expose `queue_section`, `handoff_stage`, or `linked_job_name`.

- [ ] **Step 3: Add the queue metadata fields to the schema**

```python
class ClassificationRow(BaseModel):
    ...
    handoff_stage: str | None = None
    queue_section: Literal["analysis", "in_progress", "history"] = "analysis"
    linked_job_name: str | None = None
    linked_print_job_id: int | None = None
```

- [ ] **Step 4: Add upload-row columns and mapping in `app/database.py`**

```python
_ensure_column(connection, "upload_rows", "handoff_stage", "TEXT")
_ensure_column(connection, "upload_rows", "queue_section", "TEXT NOT NULL DEFAULT 'analysis'")
_ensure_column(connection, "upload_rows", "linked_job_name", "TEXT")
_ensure_column(connection, "upload_rows", "linked_print_job_id", "INTEGER")
```

```python
    return ClassificationRow(
        ...
        handoff_stage=row["handoff_stage"],
        queue_section=row["queue_section"] or "analysis",
        linked_job_name=row["linked_job_name"],
        linked_print_job_id=row["linked_print_job_id"],
    )
```

- [ ] **Step 5: Run the targeted test and verify GREEN**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_handoff.py::test_send_to_print_marks_rows_with_history_job_link_metadata -q`

Expected: PASS.

## Task 2: Add failing tests for queue sections and history separation

**Files:**
- Modify: `tests/test_preform_handoff.py`
- Modify: `app/database.py`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Write the failing queue-snapshot separation test**

```python
def test_queue_lists_work_queue_rows_separately_from_history(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)
    persist_upload_session(
        settings,
        "session-1",
        [
            {
                "file_name": "analysis.stl",
                "stored_path": str(tmp_path / "analysis.stl"),
                "content_hash": "analysis-hash",
                "thumbnail_svg": None,
                "case_id": "CASE-A",
                "model_type": "Tooth",
                "preset": "Tooth - With Supports",
                "confidence": "high",
                "status": "Ready",
                "dimension_x_mm": None,
                "dimension_y_mm": None,
                "dimension_z_mm": None,
                "volume_ml": None,
                "review_required": False,
                "review_reason": None,
                "printer": None,
                "person": None,
                "handoff_stage": None,
                "queue_section": "analysis",
                "linked_job_name": None,
                "linked_print_job_id": None,
            },
            {
                "file_name": "history.stl",
                "stored_path": str(tmp_path / "history.stl"),
                "content_hash": "history-hash",
                "thumbnail_svg": None,
                "case_id": "CASE-B",
                "model_type": "Tooth",
                "preset": "Tooth - With Supports",
                "confidence": "high",
                "status": "Submitted",
                "dimension_x_mm": None,
                "dimension_y_mm": None,
                "dimension_z_mm": None,
                "volume_ml": None,
                "review_required": False,
                "review_reason": None,
                "printer": None,
                "person": None,
                "handoff_stage": "Queued",
                "queue_section": "history",
                "linked_job_name": "260422-001",
                "linked_print_job_id": 1,
            },
        ],
    )

    active_rows, processed_rows = list_queue_rows(settings)

    assert [row.file_name for row in active_rows] == ["analysis.stl"]
    assert [row.file_name for row in processed_rows] == ["history.stl"]
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_handoff.py::test_queue_lists_work_queue_rows_separately_from_history -q`

Expected: FAIL because `persist_upload_session()` and `list_queue_rows()` do not yet use the new workflow columns.

- [ ] **Step 3: Update persistence defaults and queue queries**

```python
                "handoff_stage": row.get("handoff_stage"),
                "queue_section": row.get("queue_section", "analysis"),
                "linked_job_name": row.get("linked_job_name"),
                "linked_print_job_id": row.get("linked_print_job_id"),
```

```python
active_rows = connection.execute(
    """
    SELECT *
    FROM upload_rows
    WHERE COALESCE(queue_section, 'analysis') != 'history'
    ORDER BY
        CASE WHEN COALESCE(queue_section, 'analysis') = 'in_progress' THEN 1 ELSE 0 END,
        CASE WHEN status = 'Needs Review' THEN 0 ELSE 1 END,
        current_event_at DESC,
        created_at,
        id
    """
).fetchall()
```

```python
processed_rows = connection.execute(
    """
    SELECT *
    FROM upload_rows
    WHERE COALESCE(queue_section, 'analysis') = 'history'
    ORDER BY current_event_at DESC, id DESC
    """
).fetchall()
```

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_handoff.py::test_queue_lists_work_queue_rows_separately_from_history -q`

Expected: PASS.

## Task 3: Add failing tests for frontend contract changes

**Files:**
- Modify: `tests/test_frontend_static.py`
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

- [ ] **Step 1: Write the failing frontend static test**

```python
def test_work_queue_renders_file_analysis_and_in_progress_sections():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert "File Analysis" in index_html
    assert "In Progress" in index_html
    assert "History" in index_html
    assert "print-queue-table" in index_html
    assert "renderWorkQueueSections" in app_js
    assert "Generating preview" in app_js
    assert ".queue-section" in styles_css
```

- [ ] **Step 2: Run the targeted static test and verify RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_work_queue_renders_file_analysis_and_in_progress_sections -q`

Expected: FAIL because the HTML still uses `Active`/`Processed` and the print queue is still card-based.

- [ ] **Step 3: Replace the queue page shell in `app/static/index.html`**

```html
<button id="work-queue-tab" class="tab-button tab-button-active" type="button" role="tab" aria-selected="true">
    Work Queue
    <span id="work-queue-count" class="tab-count">0</span>
</button>
<button id="history-tab" class="tab-button" type="button" role="tab" aria-selected="false">
    History
    <span id="history-count" class="tab-count">0</span>
</button>
```

```html
<div id="work-queue-panel" class="queue-panel hidden">
    <section class="queue-section">
        <div class="section-header">
            <div>
                <p class="eyebrow">Work Queue</p>
                <h3>File Analysis</h3>
            </div>
        </div>
        <div id="file-analysis-table" class="results-wrapper"></div>
    </section>
    <section class="queue-section queue-section-readonly">
        <div class="section-header">
            <div>
                <p class="eyebrow">Work Queue</p>
                <h3>In Progress</h3>
            </div>
        </div>
        <div id="in-progress-table" class="results-wrapper"></div>
    </section>
</div>
```

```html
<div id="print-queue-table-wrapper" class="results-wrapper">
    <table class="data-table print-queue-table">
        <thead>
            <tr>
                <th>Preview</th>
                <th>Job</th>
                <th>Cases</th>
                <th>Status</th>
                <th>Print Details</th>
            </tr>
        </thead>
        <tbody id="print-queue-body"></tbody>
    </table>
</div>
```

- [ ] **Step 4: Add the frontend helpers and table renderer**

```javascript
function rowStatusLabel(row) {
    return row.handoff_stage || getRowStatus(row);
}

function splitWorkQueueRows(rows) {
    return {
        fileAnalysis: rows.filter((row) => (row.queue_section || "analysis") !== "in_progress"),
        inProgress: rows.filter((row) => row.queue_section === "in_progress"),
    };
}
```

```javascript
function createPrintQueueRow(job) {
    const tr = document.createElement("tr");
    ...
    if (job.screenshot_url) {
        button.addEventListener("click", () => openScreenshotModal(job));
    } else {
        button.disabled = true;
        button.appendChild(Object.assign(document.createElement("div"), {
            className: "job-screenshot-placeholder",
            textContent: "Generating preview",
        }));
    }
    ...
    return tr;
}
```

- [ ] **Step 5: Run the targeted static test and verify GREEN**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_work_queue_renders_file_analysis_and_in_progress_sections -q`

Expected: PASS.

## Task 4: Add failing tests for send-to-print UX behavior

**Files:**
- Modify: `tests/test_frontend_static.py`
- Modify: `app/static/app.js`
- Modify: `app/services/print_queue_service.py`

- [ ] **Step 1: Write the failing frontend contract test**

```python
def test_send_to_print_keeps_user_on_work_queue_and_links_history_rows():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'state.activeTab = "work-queue"' in app_js
    assert "brieflyQueueRows" in app_js
    assert "highlightedJobId" in app_js
    assert "linked_job_name" in app_js
```

- [ ] **Step 2: Run the targeted static test and verify RED**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_send_to_print_keeps_user_on_work_queue_and_links_history_rows -q`

Expected: FAIL because the current send flow switches users directly to `print-queue`.

- [ ] **Step 3: Update backend handoff metadata writes**

```python
for row in manifest_rows:
    connection.execute(
        """
        UPDATE upload_rows
        SET queue_section = 'in_progress',
            handoff_stage = 'Processing',
            current_event_at = ?
        WHERE id = ?
        """,
        (now, row.row_id),
    )
```

```python
connection.execute(
    """
    UPDATE upload_rows
    SET status = 'Submitted',
        queue_section = 'history',
        handoff_stage = 'Queued',
        linked_job_name = ?,
        linked_print_job_id = ?,
        current_event_at = ?
    WHERE id = ?
    """,
    (result["job_name"], print_job_id, now, row.row_id),
)
```

- [ ] **Step 4: Update the send flow in `app/static/app.js`**

```javascript
async function sendRowsToPrint(rows) {
    state.activeTab = "work-queue";
    markRowsInProgress(rows, "Processing");
    render();
    ...
    await fetchQueue();
    await fetchPrintQueue();
    brieflyQueueRows(payload.filter((row) => row.status === "Submitted"));
    setStatus(buildSendReceipt(payload));
    render();
}
```

```javascript
function openHistoryJobLink(row) {
    if (!row.linked_job_name) {
        return;
    }
    state.activeTab = "print-queue";
    const job = state.printQueue.jobs.find((item) => item.job_name === row.linked_job_name);
    state.printQueue.highlightedJobId = job?.id || null;
    render();
}
```

- [ ] **Step 5: Run the targeted static test and verify GREEN**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py::test_send_to_print_keeps_user_on_work_queue_and_links_history_rows -q`

Expected: PASS.

## Task 5: Verification sweep

**Files:**
- Modify: none

- [ ] **Step 1: Run the focused queue UX tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py tests/test_preform_handoff.py tests/test_print_queue_polling.py -q`

Expected: PASS.

- [ ] **Step 2: Run the broader repository suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q`

Expected: PASS.

- [ ] **Step 3: Review the final diff**

Run: `git diff --stat`

Expected: diff covers schema/database metadata, handoff state updates, queue UI restructuring, print queue table rendering, and history job-link support.

## Self-Review

### Spec Coverage

This plan covers:

1. `Work Queue` with `File Analysis` + read-only `In Progress`
2. keeping the user on `Work Queue` after send
3. brief `Queued` confirmation before rows leave
4. `History` as file-level traceability with a job link
5. `Print Queue` as a table with non-clickable `Generating preview`
6. failure rows returning to the top of `File Analysis`

No approved UX requirement is left without a task.

### Placeholder Scan

Checked for unresolved `TBD`, `TODO`, and hand-wavy “handle later” steps. None remain.

### Type Consistency

The plan consistently uses:

1. `queue_section`
2. `handoff_stage`
3. `linked_job_name`
4. `linked_print_job_id`

Those names stay aligned across schema, database mapping, handoff updates, and frontend rendering.
