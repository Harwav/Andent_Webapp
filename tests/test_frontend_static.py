"""Phase 1: Frontend static contract tests (TDD)."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import textwrap


APP_JS = Path("app/static/app.js")
INDEX_HTML = Path("app/static/index.html")
STYLES_CSS = Path("app/static/styles.css")


def _extract_function_source(source: str, name: str) -> str:
    match = re.search(rf"(?:async\s+)?function\s+{name}\s*\(", source)
    if not match:
        raise AssertionError(f"Could not find function {name} in app/static/app.js")

    start = match.start()
    body_start = source.index("{", match.start())
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]

    raise AssertionError(f"Could not parse function body for {name}")


def _run_node(script: str) -> str:
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


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


def test_setup_center_displays_local_printer_status():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert 'id="preform-printer-list"' in index_html
    assert 'id="preform-printer-refresh-button"' in index_html
    assert "fetchPreformPrinters" in app_js
    assert '"/api/preform-setup/printers"' in app_js
    assert "renderPreformPrinters" in app_js
    assert "formatPrinterMaterial" in app_js
    assert "createPrinterStatusPill" in app_js
    assert "preform-printer-table" in styles_css
    assert "preform-printer-status-pill" in styles_css
    assert "preform-printer-card" not in styles_css


def test_local_printer_refresh_isolated_from_queue_refresh():
    app_js = APP_JS.read_text(encoding="utf-8")
    run_preform_action = _extract_function_source(app_js, "runPreformAction")
    bootstrap = _extract_function_source(app_js, "bootstrap")
    queue_poll_start = app_js.index("// Queue polling - auto-refresh every 10 seconds")
    queue_poll_end = app_js.index("// Print queue polling - auto-refresh every 5 seconds")
    queue_poll_block = app_js[queue_poll_start:queue_poll_end]

    assert "function schedulePreformPrinterRefresh()" in app_js
    assert "available: false" in app_js
    assert "message: error.message" in app_js
    assert "schedulePreformPrinterRefresh();" in run_preform_action
    assert "await refreshPreformPrintersQuietly();" not in run_preform_action
    assert "schedulePreformPrinterRefresh();" in queue_poll_block
    assert "await refreshPreformPrintersQuietly();" not in queue_poll_block
    assert "schedulePreformPrinterRefresh();" in bootstrap
    assert "await refreshPreformPrintersQuietly();" not in bootstrap


def test_local_printer_material_prefers_readable_name_over_code():
    app_js = APP_JS.read_text(encoding="utf-8")
    format_printer_material = _extract_function_source(app_js, "formatPrinterMaterial")
    printer_payload = {
        "name": "Form 4BL Front Desk",
        "material_code": "FLGPCL04",
        "metadata": {
            "material_name": "Clear Resin V4",
        },
    }
    script = textwrap.dedent(
        f"""
        {format_printer_material}
        const result = formatPrinterMaterial({json.dumps(printer_payload)});
        console.log(JSON.stringify(result));
        """
    )

    material = json.loads(_run_node(script))

    assert material == {"label": "Clear Resin V4", "code": "FLGPCL04"}


def test_scheduled_printer_refresh_does_not_wait_for_slow_discovery_before_continuing():
    app_js = APP_JS.read_text(encoding="utf-8")
    start_printer_refresh = _extract_function_source(app_js, "startPreformPrinterRefresh")
    commit_printer_payload = _extract_function_source(app_js, "commitPreformPrinterPayload")
    handle_printer_fetch_error = _extract_function_source(app_js, "handlePreformPrinterFetchError")
    refresh_printers_quietly = _extract_function_source(app_js, "refreshPreformPrintersQuietly")
    schedule_refresh = _extract_function_source(app_js, "schedulePreformPrinterRefresh")
    script = textwrap.dedent(
        f"""
        const timeline = [];
        const state = {{
            preformSetup: {{
                printerRefreshRequestId: 0,
                printerRefreshInFlightCount: 0,
                printers: null,
            }},
        }};

        async function fetchPreformPrinters() {{
            timeline.push("refresh-start");
            await new Promise((resolve) => setTimeout(() => {{
                timeline.push("refresh-end");
                resolve();
            }}, 30));
            return {{
                available: true,
                message: null,
                printers: [],
            }};
        }}

        function renderPreformPrinters() {{
            timeline.push("render-printers");
        }}

        {start_printer_refresh}
        {commit_printer_payload}
        {handle_printer_fetch_error}
        {refresh_printers_quietly}
        {schedule_refresh}

        (async () => {{
            schedulePreformPrinterRefresh();
            timeline.push("after-schedule");
            await new Promise((resolve) => setTimeout(resolve, 5));
            const beforeCompletion = [...timeline];
            await new Promise((resolve) => setTimeout(resolve, 50));
            console.log(JSON.stringify({{ beforeCompletion, final: timeline }}));
        }})();
        """
    )

    result = json.loads(_run_node(script))

    assert result["beforeCompletion"] == ["refresh-start", "after-schedule"]
    assert result["final"] == ["refresh-start", "after-schedule", "refresh-end", "render-printers"]


def test_scheduled_printer_refresh_skips_overlapping_fetches():
    app_js = APP_JS.read_text(encoding="utf-8")
    start_printer_refresh = _extract_function_source(app_js, "startPreformPrinterRefresh")
    commit_printer_payload = _extract_function_source(app_js, "commitPreformPrinterPayload")
    handle_printer_fetch_error = _extract_function_source(app_js, "handlePreformPrinterFetchError")
    refresh_printers_quietly = _extract_function_source(app_js, "refreshPreformPrintersQuietly")
    schedule_refresh = _extract_function_source(app_js, "schedulePreformPrinterRefresh")
    script = textwrap.dedent(
        f"""
        const timeline = [];
        const state = {{
            preformSetup: {{
                printerRefreshRequestId: 0,
                printerRefreshInFlightCount: 0,
                printers: null,
            }},
        }};
        let fetchCalls = 0;

        async function fetchPreformPrinters() {{
            fetchCalls += 1;
            timeline.push(`fetch-${{fetchCalls}}-start`);
            await new Promise((resolve) => setTimeout(() => {{
                timeline.push(`fetch-${{fetchCalls}}-end`);
                resolve();
            }}, 30));
            return {{
                available: true,
                message: null,
                printers: [{{ name: `printer-${{fetchCalls}}` }}],
            }};
        }}

        function renderPreformPrinters() {{
            timeline.push(`render-${{state.preformSetup.printers?.printers?.[0]?.name || "none"}}`);
        }}

        {start_printer_refresh}
        {commit_printer_payload}
        {handle_printer_fetch_error}
        {refresh_printers_quietly}
        {schedule_refresh}

        (async () => {{
            schedulePreformPrinterRefresh();
            schedulePreformPrinterRefresh();
            await new Promise((resolve) => setTimeout(resolve, 50));
            console.log(JSON.stringify({{
                fetchCalls,
                inFlightCount: state.preformSetup.printerRefreshInFlightCount,
                finalPrinter: state.preformSetup.printers?.printers?.[0]?.name || null,
                timeline,
            }}));
        }})();
        """
    )

    result = json.loads(_run_node(script))

    assert result["fetchCalls"] == 1
    assert result["inFlightCount"] == 0
    assert result["finalPrinter"] == "printer-1"
    assert result["timeline"] == ["fetch-1-start", "fetch-1-end", "render-printer-1"]


def test_newer_manual_printer_refresh_wins_over_older_scheduled_result():
    app_js = APP_JS.read_text(encoding="utf-8")
    fetch_preform_printers = _extract_function_source(app_js, "fetchPreformPrinters")
    start_printer_refresh = _extract_function_source(app_js, "startPreformPrinterRefresh")
    commit_printer_payload = _extract_function_source(app_js, "commitPreformPrinterPayload")
    handle_printer_fetch_error = _extract_function_source(app_js, "handlePreformPrinterFetchError")
    refresh_printers_quietly = _extract_function_source(app_js, "refreshPreformPrintersQuietly")
    schedule_refresh = _extract_function_source(app_js, "schedulePreformPrinterRefresh")
    refresh_printers = _extract_function_source(app_js, "refreshPreformPrinters")
    script = textwrap.dedent(
        f"""
        const state = {{
            preformSetup: {{
                printers: null,
                printersLoading: false,
                printerRefreshRequestId: 0,
            }},
        }};
        const renders = [];
        const statusMessages = [];
        const responses = [
            {{
                delay: 40,
                payload: {{
                    available: true,
                    message: null,
                    printers: [{{ name: "scheduled-stale" }}],
                }},
            }},
            {{
                delay: 10,
                payload: {{
                    available: true,
                    message: null,
                    printers: [{{ name: "manual-newer" }}],
                }},
            }},
        ];

        function renderPreformSetup() {{
            renders.push({{
                source: "setup",
                value: state.preformSetup.printers?.printers?.[0]?.name || null,
            }});
        }}

        function renderPreformPrinters() {{
            renders.push({{
                source: "printers",
                value: state.preformSetup.printers?.printers?.[0]?.name || null,
            }});
        }}

        function render() {{
            renders.push({{
                source: "render",
                value: state.preformSetup.printers?.printers?.[0]?.name || null,
            }});
        }}

        function setStatus(message, isError = false) {{
            statusMessages.push({{ message, isError }});
        }}

        async function fetch(url) {{
            const next = responses.shift();
            await new Promise((resolve) => setTimeout(resolve, next.delay));
            return {{
                ok: true,
                async json() {{
                    return next.payload;
                }},
            }};
        }}

        {fetch_preform_printers}
        {start_printer_refresh}
        {commit_printer_payload}
        {handle_printer_fetch_error}
        {refresh_printers_quietly}
        {schedule_refresh}
        {refresh_printers}

        (async () => {{
            schedulePreformPrinterRefresh();
            await new Promise((resolve) => setTimeout(resolve, 1));
            await refreshPreformPrinters();
            await new Promise((resolve) => setTimeout(resolve, 60));
            console.log(JSON.stringify({{
                finalPrinter: state.preformSetup.printers?.printers?.[0]?.name || null,
                lastRenderedPrinter: renders.at(-1)?.value || null,
                renders,
                statusMessages,
            }}));
        }})();
        """
    )

    result = json.loads(_run_node(script))

    assert result["finalPrinter"] == "manual-newer"
    assert result["lastRenderedPrinter"] == "manual-newer"
