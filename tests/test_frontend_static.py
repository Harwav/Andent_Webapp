"""Phase 1: Frontend static contract tests (TDD)."""

from __future__ import annotations

from pathlib import Path


APP_JS = Path("app/static/app.js")
INDEX_HTML = Path("app/static/index.html")
STYLES_CSS = Path("app/static/styles.css")


def test_primary_upload_action_does_not_use_browser_folder_picker_prompt():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "webkitdirectory" not in index_html
    assert "folder-input" not in index_html
    assert "folderInput" not in app_js


def test_pending_row_preview_uses_local_file_blob_during_analysis():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "row.file.arrayBuffer()" in app_js
    assert "Preview unavailable while status is" not in app_js


def test_analyzing_status_has_motion_affordance():
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert "@keyframes analyzing-pulse" in styles_css
    assert ".status-analyzing::before" in styles_css


def test_in_progress_handoff_statuses_have_motion_affordance():
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert ".status-calculating-volume" in styles_css
    assert ".status-processing" in styles_css
    assert ".status-importing" in styles_css
    assert ".status-layout" in styles_css
    assert ".status-validating" in styles_css
    assert ".status-calculating-volume::before" in styles_css
    assert ".status-processing::before" in styles_css


def test_thumbnail_preview_uses_threejs_snapshot_cache():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "thumbnailSnapshots" in app_js
    assert "queueThumbnailSnapshot(row)" in app_js
    assert "renderStlSnapshotPng" in app_js
    assert "preserveDrawingBuffer: true" in app_js
    assert ".toDataURL(\"image/png\")" in app_js
    assert "localStorage.setItem" in app_js
    assert "localStorage.getItem" in app_js
    assert "image.src = row.thumbnail_url" not in app_js


def test_send_to_print_keeps_user_on_work_queue_and_highlights_linked_jobs_later():
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert 'state.activeTab = "work-queue"' in app_js
    assert "brieflyQueueRows" in app_js
    assert "highlightedJobId" in app_js
    assert "Moved ${submittedCount} file(s) into In Progress." in app_js
    assert "openHistoryJobLink" in app_js
    assert "print-job-row-highlight" in styles_css


def test_work_queue_replaces_active_processed_tabs_with_sectioned_workflow():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert "Work Queue" in index_html
    assert "File Analysis" in index_html
    assert "In Progress" in index_html
    assert "History" in index_html
    assert "print-queue-body" in index_html
    assert 'state.activeTab = "work-queue"' in app_js
    assert "renderWorkQueueSections" in app_js
    assert "Generating preview" in app_js
    assert ".queue-section" in styles_css


def test_in_progress_rows_expose_individual_remove_without_bulk_editing():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "Processing or waiting for print handoff. Remove only if this job should be abandoned." in index_html
    assert '<th class="col-remove">Remove</th>' in index_html
    assert "elements.inProgressBody.appendChild(tr)" in app_js
    assert "removeCell.appendChild(createRemoveCell(row))" in app_js
    assert "if ((row.queue_section || \"analysis\") === \"in_progress\")" in app_js


def test_send_to_print_does_not_gate_on_calculating_volume():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'return "Calculating..."' in app_js
    assert 'return !row.is_temp && !isRowPendingDelete(row) && row.status === "Ready";' in app_js
    assert 'row.volume_ml == null ? "Calculating Volume" : stage' in app_js


def test_removal_undo_window_is_five_seconds():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "const DELETE_UNDO_MS = 5000;" in app_js


def test_active_work_queue_exposes_printer_group_selector():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")

    assert '<th class="col-printer">Printer</th>' in index_html
    assert 'const PRINTER_OPTIONS = ["Form 4BL", "Form 4B"];' in app_js
    assert "function createPrinterSelect(row)" in app_js
    assert 'select.dataset.testid = "printer-select";' in app_js
    assert "printer: row.printer || null" in app_js


def test_bulk_work_queue_exposes_printer_group_selector():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "bulkPrinterValue" in app_js
    assert 'printerSelect.setAttribute("aria-label", "Change Printer");' in app_js
    assert 'printerSelect.dataset.testid = "bulk-printer-select";' in app_js
    assert "PRINTER_OPTIONS.forEach" in app_js
    assert "printer: printer || null" in app_js


def test_print_queue_displays_holding_density_cutoff_and_release():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "function formatDensity(value)" in app_js
    assert "hold_cutoff_at" in app_js
    assert "density_target" in app_js
    assert 'createJobDetailItem("Target:", formatDensity(job.density_target))' in app_js
    assert 'createJobDetailItem("Hold Reason:", job.hold_reason)' in app_js
    assert 'createJobDetailItem("Release Reason:", job.release_reason)' in app_js
    assert "Release now" in app_js
    assert "/release-now" in app_js


def test_setup_center_exposes_temporary_virtual_printer_toggle():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert 'id="preform-dispatch-toggle"' in index_html
    assert "Virtual printer debug" in index_html
    assert "fetchDispatchMode" in app_js
    assert "setDispatchMode" in app_js
    assert '"/api/preform-setup/dispatch-mode"' in app_js
    assert ".dispatch-toggle" in styles_css
