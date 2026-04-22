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


def test_send_to_print_does_not_gate_on_calculating_volume():
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'return "Calculating..."' in app_js
    assert 'return !row.is_temp && !isRowPendingDelete(row) && row.status === "Ready";' in app_js
    assert 'row.volume_ml == null ? "Calculating Volume" : stage' in app_js
