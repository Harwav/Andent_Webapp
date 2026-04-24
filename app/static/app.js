const MODEL_TYPES = [
    "Ortho - Solid",
    "Ortho - Hollow",
    "Die",
    "Tooth",
    "Splint",
    "Antagonist",
];

const DEFAULT_PRESET_BY_MODEL = {
    "Ortho - Solid": "Ortho Solid - Flat, No Supports",
    "Ortho - Hollow": "Ortho Hollow - Flat, No Supports",
    Die: "Die - Flat, No Supports",
    Tooth: "Tooth - With Supports",
    Splint: "Splint - Flat, No Supports",
    Antagonist: "Ortho Solid - Flat, No Supports",
};

const PRESET_OPTIONS = [...new Set(Object.values(DEFAULT_PRESET_BY_MODEL))];

const ACTIVE_STATUSES = [
    "Queued",
    "Uploading",
    "Analyzing",
    "Ready",
    "Check",
    "Needs Review",
    "Duplicate",
    "Locked",
];

const PAGE_SIZE = 50;
const MAX_CONCURRENT_UPLOADS = 3;
const DELETE_UNDO_MS = 10000;
const PRINT_QUEUE_POLL_INTERVAL = 5000; // 5 seconds
const THUMBNAIL_SNAPSHOT_STORAGE_PREFIX = "andent:thumbnail-snapshot:";

const state = {
    activeTab: "work-queue",
    activeRows: [],
    processedRows: [],
    pendingRows: [],
    inflightUploads: 0,
    selectedIds: new Set(),
    activeFilters: new Set(),
    activePage: 1,
    processedPage: 1,
    rowLocks: new Set(),
    pendingDeletes: new Map(),
    pendingBulkDelete: null,
    bulkModelTypeValue: "",
    bulkPresetValue: "",
    pickerOpen: false,
    pickerReleaseId: null,
    preview: {
        renderer: null,
        frameId: null,
        cleanup: null,
    },
    thumbnailSnapshots: {
        cache: new Map(),
        pending: new Set(),
        queue: [],
        active: 0,
        maxActive: 2,
    },
    printQueue: {
        jobs: [],
        page: 1,
        expandedCases: new Set(),
        highlightedJobId: null,
    },
    transientQueuedRows: new Map(),
    preformSetup: {
        status: null,
        loading: false,
        wizardDismissed: false,
    },
};

const elements = {
    activeBody: document.getElementById("active-body"),
    inProgressBody: document.getElementById("in-progress-body"),
    activePaginationBottom: document.getElementById("active-pagination-bottom"),
    activePaginationTop: document.getElementById("active-pagination-top"),
    bulkActions: document.getElementById("bulk-actions"),
    closePreview: document.getElementById("close-preview"),
    dropzone: document.getElementById("dropzone"),
    emptyState: document.getElementById("empty-state"),
    fileInput: document.getElementById("file-input"),
    previewCaption: document.getElementById("preview-caption"),
    previewModal: document.getElementById("preview-modal"),
    previewTitle: document.getElementById("preview-title"),
    previewViewer: document.getElementById("preview-viewer"),
    preformBanner: document.getElementById("preform-banner"),
    preformInstallButton: document.getElementById("preform-install-button"),
    preformLastCheck: document.getElementById("preform-last-check"),
    preformReadinessPill: document.getElementById("preform-readiness-pill"),
    preformRecheckButton: document.getElementById("preform-recheck-button"),
    preformRestartButton: document.getElementById("preform-restart-button"),
    preformSetupPanel: document.getElementById("preform-setup-panel"),
    preformStartButton: document.getElementById("preform-start-button"),
    preformStopButton: document.getElementById("preform-stop-button"),
    preformSummary: document.getElementById("preform-summary"),
    preformVersion: document.getElementById("preform-version"),
    preformVersionRange: document.getElementById("preform-version-range"),
    preformWizard: document.getElementById("preform-wizard"),
    preformZipInput: document.getElementById("preform-zip-input"),
    historyBody: document.getElementById("history-body"),
    historyCount: document.getElementById("history-count"),
    historyPanel: document.getElementById("history-panel"),
    historyPaginationBottom: document.getElementById("history-pagination-bottom"),
    historyPaginationTop: document.getElementById("history-pagination-top"),
    historyTab: document.getElementById("history-tab"),
    queueActionButton: document.getElementById("queue-action-button"),
    selectPageCheckbox: document.getElementById("select-page-checkbox"),
    selectionNote: document.getElementById("selection-note"),
    statusLegend: document.getElementById("status-legend"),
    statusText: document.getElementById("status-text"),
    workQueueCount: document.getElementById("work-queue-count"),
    workQueuePanel: document.getElementById("work-queue-panel"),
    workQueueTab: document.getElementById("work-queue-tab"),
    printQueueTab: document.getElementById("print-queue-tab"),
    printQueueCount: document.getElementById("print-queue-count"),
    printQueuePanel: document.getElementById("print-queue-panel"),
    printQueueBody: document.getElementById("print-queue-body"),
    printQueueEmpty: document.getElementById("print-queue-empty"),
    printQueuePaginationTop: document.getElementById("print-queue-pagination-top"),
    printQueuePaginationBottom: document.getElementById("print-queue-pagination-bottom"),
    screenshotModal: document.getElementById("screenshot-modal"),
    screenshotTitle: document.getElementById("screenshot-title"),
    screenshotViewer: document.getElementById("screenshot-viewer"),
    screenshotImage: document.getElementById("screenshot-image"),
    screenshotCaption: document.getElementById("screenshot-caption"),
    closeScreenshot: document.getElementById("close-screenshot"),
};

async function ensurePreviewDependencies() {
    if (window.__andentThreeDeps) {
        return window.__andentThreeDeps;
    }

    const THREE = await import("https://esm.sh/three@0.161.0");
    const loaderModule = await import("https://esm.sh/three@0.161.0/examples/jsm/loaders/STLLoader.js");
    window.__andentThreeDeps = {
        THREE,
        STLLoader: loaderModule.STLLoader,
    };
    return window.__andentThreeDeps;
}

function setStatus(message, isError = false) {
    elements.statusText.textContent = message;
    elements.statusText.classList.toggle("error-text", isError);
}

function getPreformSetupStatus() {
    return state.preformSetup.status;
}

function canPrint() {
    return getPreformSetupStatus()?.readiness === "ready";
}

function formatPreformRange(status) {
    if (!status) {
        return "-";
    }
    return status.expected_version_max
        ? `${status.expected_version_min} to ${status.expected_version_max}`
        : `${status.expected_version_min}+`;
}

function preformReadinessLabel(status) {
    if (!status) {
        return "Checking";
    }
    switch (status.readiness) {
        case "ready":
            return "Ready";
        case "not_installed":
            return "Not Installed";
        case "installed_not_running":
            return "Stopped";
        case "incompatible_version":
            return "Update Required";
        default:
            return "Needs Attention";
    }
}

function preformReadinessTone(status) {
    if (!status) {
        return "neutral";
    }
    switch (status.readiness) {
        case "ready":
            return "ready";
        case "incompatible_version":
            return "warn";
        case "not_installed":
        case "installed_not_running":
            return "info";
        default:
            return "danger";
    }
}

function describePreformSetup(status) {
    if (!status) {
        return "Checking managed PreFormServer readiness.";
    }
    switch (status.readiness) {
        case "ready":
            return `Managed PreFormServer is healthy and ready for print handoff on the configured local port.`;
        case "not_installed":
            return "No managed PreFormServer install exists yet. Select a local ZIP package to install the canonical copy used by Andent Web.";
        case "installed_not_running":
            return status.last_error_message
                ? `A managed install exists, but the local API is not reachable. ${status.last_error_message}`
                : "A managed install exists, but the local API is not reachable. Start the managed service or replace it with a newer ZIP.";
        case "incompatible_version":
            return status.last_error_message
                ? status.last_error_message
                : "The managed PreFormServer version is outside the supported range. Replace it with a compatible ZIP before printing.";
        default:
            return status.last_error_message || "PreFormServer needs attention before print handoff can continue.";
    }
}

function openPreformWizard() {
    state.preformSetup.wizardDismissed = false;
    renderPreformWizard();
}

function dismissPreformWizard() {
    state.preformSetup.wizardDismissed = true;
    renderPreformWizard();
}

async function fetchPreformSetupStatus() {
    const response = await fetch("/api/preform-setup/status");
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.detail || "Could not load PreFormServer setup status.");
    }
    state.preformSetup.status = payload;
}

async function runPreformAction(url, options, successMessage) {
    state.preformSetup.loading = true;
    renderPreformSetup();
    try {
        const response = await fetch(url, options);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || "PreFormServer action failed.");
        }
        state.preformSetup.status = payload.status;
        setStatus(payload.message || successMessage);
    } catch (error) {
        setStatus(error.message, true);
    } finally {
        state.preformSetup.loading = false;
        render();
    }
}

function renderPreformSetup() {
    const status = getPreformSetupStatus();
    const tone = preformReadinessTone(status);
    const label = preformReadinessLabel(status);
    const summary = describePreformSetup(status);
    const blocked = status && status.readiness !== "ready";

    elements.preformReadinessPill.textContent = label;
    elements.preformReadinessPill.className = `status-pill status-pill-${tone}`;
    elements.preformSetupPanel.classList.toggle("setup-panel-ready", status?.readiness === "ready");
    elements.preformSummary.textContent = summary;
    elements.preformVersion.textContent = status?.detected_version || "-";
    elements.preformVersionRange.textContent = formatPreformRange(status);
    elements.preformLastCheck.textContent = formatDate(status?.last_health_check_at || "");
    elements.preformBanner.classList.toggle("hidden", !blocked);
    elements.preformBanner.textContent = blocked
        ? `Print handoff is blocked until PreFormServer is ${label.toLowerCase()}.`
        : "";

    elements.preformStartButton.disabled = state.preformSetup.loading || !status || status.readiness === "ready";
    elements.preformStopButton.disabled = state.preformSetup.loading || !status || status.readiness === "not_installed";
    elements.preformRestartButton.disabled = state.preformSetup.loading || !status || status.readiness === "not_installed";
    elements.preformRecheckButton.disabled = state.preformSetup.loading || !status;
    elements.preformInstallButton.disabled = state.preformSetup.loading;
    renderPreformWizard();
}

function renderPreformWizard() {
    const status = getPreformSetupStatus();
    const shouldShow = status && status.readiness !== "ready" && !state.preformSetup.wizardDismissed;
    elements.preformWizard.classList.toggle("hidden", !shouldShow);
    elements.preformWizard.setAttribute("aria-hidden", String(!shouldShow));
    if (!shouldShow) {
        elements.preformWizard.innerHTML = "";
        return;
    }

    elements.preformWizard.innerHTML = `
        <div class="wizard-backdrop" data-close-modal="wizard"></div>
        <div class="wizard-card" role="dialog" aria-modal="true" aria-labelledby="preform-wizard-title">
            <div class="wizard-header">
                <div>
                    <p class="eyebrow">PreFormServer Setup</p>
                    <h2 id="preform-wizard-title">${preformReadinessLabel(status)}</h2>
                </div>
                <button type="button" class="ghost-button" data-wizard-dismiss="true">Continue Without Printing</button>
            </div>
            <p class="setup-summary">${describePreformSetup(status)}</p>
            <div class="wizard-checklist">
                <div class="wizard-checklist-item">Supported range: ${formatPreformRange(status)}</div>
                <div class="wizard-checklist-item">Detected version: ${status.detected_version || "-"}</div>
            </div>
            <div class="wizard-actions">
                <button type="button" class="primary-button" data-preform-install="true">Select ZIP Package</button>
                <button type="button" class="secondary-button" data-preform-recheck="true">Re-check</button>
            </div>
        </div>
    `;
}

function releasePickerGuard() {
    state.pickerOpen = false;
    if (state.pickerReleaseId) {
        window.clearTimeout(state.pickerReleaseId);
        state.pickerReleaseId = null;
    }
}

function getDefaultPreset(modelType) {
    return DEFAULT_PRESET_BY_MODEL[modelType] || "";
}

function schedulePickerGuardRelease(delay = 200) {
    if (state.pickerReleaseId) {
        window.clearTimeout(state.pickerReleaseId);
    }
    state.pickerReleaseId = window.setTimeout(() => {
        releasePickerGuard();
    }, delay);
}

function openPicker(input) {
    if (state.pickerOpen) {
        return;
    }

    state.pickerOpen = true;
    schedulePickerGuardRelease(1200);
    try {
        if (typeof input.showPicker === "function") {
            input.showPicker();
            return;
        }
        input.click();
    } catch (error) {
        releasePickerGuard();
        throw error;
    }
}

function normalizeRow(row) {
    const defaultPreset = getDefaultPreset(row.model_type);
    return {
        ...row,
        row_id: row.row_id,
        preset_overridden: Boolean(row.preset && defaultPreset && row.preset !== defaultPreset),
        is_temp: false,
    };
}

function compareActiveRows(left, right) {
    const leftCase = (left.case_id || "~").toLowerCase();
    const rightCase = (right.case_id || "~").toLowerCase();
    if (leftCase !== rightCase) {
        return leftCase.localeCompare(rightCase);
    }
    return (left.created_at || "").localeCompare(right.created_at || "") || String(left.row_id).localeCompare(String(right.row_id));
}

function compareProcessedRows(left, right) {
    return (right.current_event_at || "").localeCompare(left.current_event_at || "") || (right.row_id - left.row_id);
}

function sortRows() {
    state.activeRows.sort(compareActiveRows);
    state.processedRows.sort(compareProcessedRows);
}

function getCombinedActiveRows() {
    return [
        ...state.pendingRows,
        ...state.activeRows.filter((row) => (row.queue_section || "analysis") !== "in_progress"),
    ];
}

function getInProgressRows() {
    return [
        ...state.activeRows.filter((row) => (row.queue_section || "analysis") === "in_progress"),
        ...state.transientQueuedRows.values(),
    ];
}

function rowStatusLabel(row) {
    return row.handoff_stage || getRowStatus(row);
}

function getFilteredActiveRows() {
    const rows = getCombinedActiveRows();
    if (state.activeFilters.size === 0) {
        return rows;
    }
    return rows.filter((row) => state.activeFilters.has(getRowStatus(row)));
}

function getPagedRows(rows, page) {
    const start = (page - 1) * PAGE_SIZE;
    return rows.slice(start, start + PAGE_SIZE);
}

function getRowKey(row) {
    return row.is_temp ? row.temp_id : `row-${row.row_id}`;
}

function getThumbnailSnapshotKey(row) {
    return row.is_temp ? `temp:${row.temp_id}:${row.file_name}` : `row:${row.row_id}:${row.file_name}`;
}

function getStoredThumbnailSnapshot(key) {
    try {
        return window.localStorage.getItem(`${THUMBNAIL_SNAPSHOT_STORAGE_PREFIX}${key}`);
    } catch (error) {
        return null;
    }
}

function storeThumbnailSnapshot(key, dataUrl) {
    try {
        window.localStorage.setItem(`${THUMBNAIL_SNAPSHOT_STORAGE_PREFIX}${key}`, dataUrl);
    } catch (error) {
        // Storage may be full or disabled; in-memory cache still covers the current session.
    }
}

function getRowStatus(row) {
    if (!row.is_temp && state.rowLocks.has(row.row_id)) {
        return "Locked";
    }
    return row.status;
}

function isRowPendingDelete(row) {
    if (state.pendingDeletes.has(getRowKey(row))) {
        return true;
    }
    return Boolean(!row.is_temp && state.pendingBulkDelete?.rowIds.has(row.row_id));
}

function isEditableActiveRow(row) {
    if (row.is_temp || isRowPendingDelete(row)) {
        return false;
    }
    if ((row.queue_section || "analysis") === "in_progress") {
        return false;
    }
    const status = getRowStatus(row);
    return !["Submitted", "Printed", "Locked"].includes(status);
}

function isReadyForPrint(row) {
    return !row.is_temp && !isRowPendingDelete(row) && row.status === "Ready";
}

function isDuplicateActionable(row) {
    return !row.is_temp && !isRowPendingDelete(row) && row.status === "Duplicate";
}

function getSelectedRows() {
    return state.activeRows.filter((row) => state.selectedIds.has(row.row_id));
}

function getRowIds(rows) {
    return rows.map((row) => row.row_id);
}

function syncSelection() {
    const validIds = new Set(state.activeRows.filter(isEditableActiveRow).map((row) => row.row_id));
    state.selectedIds = new Set([...state.selectedIds].filter((rowId) => validIds.has(rowId)));
}

function clampPages() {
    const activePages = Math.max(1, Math.ceil(getFilteredActiveRows().length / PAGE_SIZE));
    const processedPages = Math.max(1, Math.ceil(state.processedRows.length / PAGE_SIZE));
    state.activePage = Math.min(state.activePage, activePages);
    state.processedPage = Math.min(state.processedPage, processedPages);
}

async function fetchQueue() {
    const response = await fetch("/api/uploads/queue");
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.detail || "Could not load queue.");
    }

    state.activeRows = payload.active_rows.map(normalizeRow);
    state.processedRows = payload.processed_rows.map(normalizeRow);
    sortRows();
    syncSelection();
    clampPages();
}

async function fetchPrintQueue() {
    try {
        const response = await fetch("/api/print-queue/jobs");
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || "Could not load print queue.");
        }
        state.printQueue.jobs = payload.jobs || [];
        const totalPages = Math.max(1, Math.ceil(state.printQueue.jobs.length / PAGE_SIZE));
        state.printQueue.page = Math.min(state.printQueue.page, totalPages);
    } catch (error) {
        console.error("Print queue fetch error:", error.message);
        state.printQueue.jobs = [];
    }
}

function formatDimensions(dimensions) {
    if (!dimensions) {
        return "Unavailable";
    }
    return `${dimensions.x_mm.toFixed(1)} x ${dimensions.y_mm.toFixed(1)} x ${dimensions.z_mm.toFixed(1)} mm`;
}

function formatVolume(row) {
    if (typeof row.volume_ml !== "number") {
        return "Calculating...";
    }
    return `${row.volume_ml.toFixed(2)} mL`;
}

function formatDate(value) {
    if (!value) {
        return "-";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function createChip(status) {
    const span = document.createElement("span");
    const safeClass = status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    span.className = `status-chip status-${safeClass}`;
    span.textContent = status;
    return span;
}

function updateSelectionNote(message) {
    if (!message) {
        elements.selectionNote.textContent = "";
        elements.selectionNote.classList.add("hidden");
        return;
    }
    elements.selectionNote.textContent = message;
    elements.selectionNote.classList.remove("hidden");
}

function buildPageSelectionInfo(pageRows, filteredRows) {
    const eligibleRows = pageRows.filter(isEditableActiveRow);
    const excludedCaseIds = new Set();
    const totalByCase = new Map();
    const pageByCase = new Map();

    filteredRows.forEach((row) => {
        if (!row.case_id || !isEditableActiveRow(row)) {
            return;
        }
        totalByCase.set(row.case_id, (totalByCase.get(row.case_id) || 0) + 1);
    });
    eligibleRows.forEach((row) => {
        if (!row.case_id) {
            return;
        }
        pageByCase.set(row.case_id, (pageByCase.get(row.case_id) || 0) + 1);
    });

    const rowIds = [];
    eligibleRows.forEach((row) => {
        if (row.case_id && totalByCase.get(row.case_id) !== pageByCase.get(row.case_id)) {
            excludedCaseIds.add(row.case_id);
            return;
        }
        rowIds.push(row.row_id);
    });

    return {
        rowIds,
        excludedCases: [...excludedCaseIds],
    };
}

function toggleSelectPage(checked) {
    const filteredRows = getFilteredActiveRows();
    const pageRows = getPagedRows(filteredRows, state.activePage);
    const info = buildPageSelectionInfo(pageRows, filteredRows);

    if (checked) {
        info.rowIds.forEach((rowId) => state.selectedIds.add(rowId));
    } else {
        info.rowIds.forEach((rowId) => state.selectedIds.delete(rowId));
    }

    if (info.excludedCases.length > 0) {
        updateSelectionNote(`${info.excludedCases.length} case group(s) were skipped because they span more than one page.`);
    } else {
        updateSelectionNote("");
    }
    render();
}

function toggleRowSelection(row, checked) {
    if (!isEditableActiveRow(row)) {
        return;
    }

    if (!checked) {
        state.selectedIds.delete(row.row_id);
        render();
        return;
    }

    if (!row.case_id) {
        state.selectedIds.add(row.row_id);
        render();
        return;
    }

    state.activeRows
        .filter((candidate) => candidate.case_id === row.case_id && isEditableActiveRow(candidate))
        .forEach((candidate) => state.selectedIds.add(candidate.row_id));
    render();
}

function setRowLock(rowId, locked, shouldRender = true) {
    if (locked) {
        state.rowLocks.add(rowId);
    } else {
        state.rowLocks.delete(rowId);
    }
    if (shouldRender) {
        render();
    }
}

async function persistRow(row) {
    if (row.is_temp) {
        return;
    }

    try {
        const response = await fetch(`/api/uploads/rows/${row.row_id}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                model_type: row.model_type,
                preset: row.preset || null,
            }),
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || "Could not save row.");
        }

        const index = state.activeRows.findIndex((candidate) => candidate.row_id === row.row_id);
        if (index >= 0) {
            state.activeRows[index] = normalizeRow(payload);
            sortRows();
        }
        setStatus(`Saved ${row.file_name}.`);
    } catch (error) {
        setStatus(error.message, true);
    } finally {
        setRowLock(row.row_id, false);
        render();
    }
}

function createModelTypeSelect(row) {
    const select = document.createElement("select");
    select.dataset.testid = "model-type-select";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select";
    placeholder.hidden = true;
    placeholder.selected = !row.model_type;
    select.appendChild(placeholder);

    MODEL_TYPES.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = row.model_type === optionValue;
        select.appendChild(option);
    });

    select.disabled = row.is_temp || isRowPendingDelete(row) || row.status === "Submitted";
    select.addEventListener("focus", () => {
        if (!row.is_temp) {
            setRowLock(row.row_id, true, false);
        }
    });
    select.addEventListener("blur", () => {
        if (!row.is_temp) {
            setRowLock(row.row_id, false);
        }
    });
    select.addEventListener("change", (event) => {
        row.model_type = event.target.value || null;
        if (!row.preset_overridden) {
            row.preset = getDefaultPreset(row.model_type);
        }
        row.preset_overridden = Boolean(
            row.preset &&
            row.model_type &&
            row.preset !== getDefaultPreset(row.model_type)
        );
        render();
        persistRow(row);
    });
    return select;
}

function createPresetSelect(row) {
    const select = document.createElement("select");
    select.dataset.testid = "preset-select";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select";
    placeholder.hidden = true;
    placeholder.selected = !row.preset;
    select.appendChild(placeholder);

    PRESET_OPTIONS.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = row.preset === optionValue;
        select.appendChild(option);
    });

    select.disabled = row.is_temp || isRowPendingDelete(row) || row.status === "Submitted";
    select.addEventListener("focus", () => {
        if (!row.is_temp) {
            setRowLock(row.row_id, true, false);
        }
    });
    select.addEventListener("blur", () => {
        if (!row.is_temp) {
            setRowLock(row.row_id, false);
        }
    });
    select.addEventListener("change", (event) => {
        row.preset = event.target.value || "";
        row.preset_overridden = Boolean(
            row.preset &&
            row.model_type &&
            row.preset !== getDefaultPreset(row.model_type)
        );
        render();
        persistRow(row);
    });
    return select;
}

function createThumbnail(row) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "thumbnail-button";
    const canPreview = Boolean((row.is_temp && row.file) || row.file_url);
    button.disabled = !canPreview;
    button.addEventListener("click", () => openPreview(row));
    const snapshotKey = getThumbnailSnapshotKey(row);
    let snapshot = state.thumbnailSnapshots.cache.get(snapshotKey);
    if (!snapshot) {
        snapshot = getStoredThumbnailSnapshot(snapshotKey);
        if (snapshot) {
            state.thumbnailSnapshots.cache.set(snapshotKey, snapshot);
        }
    }
    if (snapshot) {
        const image = document.createElement("img");
        image.src = snapshot;
        image.alt = `${row.file_name} preview`;
        button.appendChild(image);
    } else {
        const placeholder = document.createElement("div");
        placeholder.className = "thumbnail-placeholder";
        placeholder.textContent = canPreview ? "Rendering" : "STL";
        button.appendChild(placeholder);
        queueThumbnailSnapshot(row);
    }
    return button;
}

async function loadStlBuffer(row) {
    if (row.is_temp) {
        return row.file.arrayBuffer();
    }
    const response = await fetch(row.file_url);
    if (!response.ok) {
        throw new Error("STL could not be loaded.");
    }
    return response.arrayBuffer();
}

async function renderStlSnapshotPng(row, size = 160) {
    const { THREE, STLLoader } = await ensurePreviewDependencies();
    const buffer = await loadStlBuffer(row);
    const loader = new STLLoader();
    const geometry = loader.parse(buffer);
    geometry.computeBoundingBox();
    geometry.center();
    geometry.computeVertexNormals();

    const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: true,
    });
    renderer.setPixelRatio(1);
    renderer.setSize(size, size, false);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8f3ec);
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 5000);
    scene.add(new THREE.AmbientLight(0xffffff, 1.15));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.7);
    keyLight.position.set(45, 60, 110);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xfff2df, 0.9);
    fillLight.position.set(-60, -40, 80);
    scene.add(fillLight);

    const material = new THREE.MeshStandardMaterial({
        color: 0xff7a2b,
        metalness: 0.08,
        roughness: 0.5,
    });
    const mesh = new THREE.Mesh(geometry, material);
    const group = new THREE.Group();
    group.rotation.set(-0.58, -0.62, 0.08);
    group.add(mesh);
    scene.add(group);

    const bounds = geometry.boundingBox;
    const modelSize = new THREE.Vector3();
    bounds.getSize(modelSize);
    const maxDimension = Math.max(modelSize.x, modelSize.y, modelSize.z) || 1;
    camera.position.set(0, maxDimension * 0.16, maxDimension * 2.35);
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);
    const dataUrl = renderer.domElement.toDataURL("image/png");

    geometry.dispose();
    material.dispose();
    renderer.dispose();
    return dataUrl;
}

function queueThumbnailSnapshot(row) {
    const canPreview = Boolean((row.is_temp && row.file) || row.file_url);
    if (!canPreview) {
        return;
    }
    const key = getThumbnailSnapshotKey(row);
    if (state.thumbnailSnapshots.cache.has(key) || state.thumbnailSnapshots.pending.has(key)) {
        return;
    }
    state.thumbnailSnapshots.pending.add(key);
    state.thumbnailSnapshots.queue.push({ key, row });
    pumpThumbnailSnapshotQueue();
}

function pumpThumbnailSnapshotQueue() {
    while (
        state.thumbnailSnapshots.active < state.thumbnailSnapshots.maxActive
        && state.thumbnailSnapshots.queue.length > 0
    ) {
        const job = state.thumbnailSnapshots.queue.shift();
        state.thumbnailSnapshots.active += 1;
        renderStlSnapshotPng(job.row)
            .then((dataUrl) => {
                state.thumbnailSnapshots.cache.set(job.key, dataUrl);
                storeThumbnailSnapshot(job.key, dataUrl);
            })
            .catch(() => {
                state.thumbnailSnapshots.cache.delete(job.key);
            })
            .finally(() => {
                state.thumbnailSnapshots.pending.delete(job.key);
                state.thumbnailSnapshots.active = Math.max(0, state.thumbnailSnapshots.active - 1);
                render();
                pumpThumbnailSnapshotQueue();
            });
    }
}

function startDeleteCountdown(row) {
    if (state.pendingBulkDelete) {
        return;
    }
    const key = getRowKey(row);
    if (state.pendingDeletes.has(key)) {
        return;
    }

    const timeoutId = window.setTimeout(async () => {
        state.pendingDeletes.delete(key);

        if (row.is_temp) {
            if (row.abortController) {
                row.deleteRequested = true;
                row.abortController.abort();
            }
            state.pendingRows = state.pendingRows.filter((candidate) => candidate.temp_id !== row.temp_id);
            render();
            return;
        }

        try {
            const response = await fetch(`/api/uploads/rows/${row.row_id}`, {
                method: "DELETE",
            });
            if (!response.ok) {
                const payload = await response.json();
                throw new Error(payload.detail || "Could not delete row.");
            }
            await fetchQueue();
            setStatus(`Removed ${row.file_name}.`);
        } catch (error) {
            setStatus(error.message, true);
        } finally {
            render();
        }
    }, DELETE_UNDO_MS);

    state.pendingDeletes.set(key, {
        expiresAt: Date.now() + DELETE_UNDO_MS,
        timeoutId,
    });
    render();
}

function undoDelete(row) {
    const key = getRowKey(row);
    const pending = state.pendingDeletes.get(key);
    if (!pending) {
        return;
    }
    window.clearTimeout(pending.timeoutId);
    state.pendingDeletes.delete(key);
    render();
}

function createRemoveCell(row) {
    const container = document.createElement("div");
    container.className = "remove-cell";
    const pending = state.pendingDeletes.get(getRowKey(row));
    if (pending) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "undo-button";
        button.textContent = "Undo";
        button.addEventListener("click", () => undoDelete(row));
        const timer = document.createElement("div");
        timer.className = "undo-timer";
        const remaining = Math.max(0, pending.expiresAt - Date.now());
        const bar = document.createElement("span");
        bar.style.width = `${(remaining / DELETE_UNDO_MS) * 100}%`;
        timer.appendChild(bar);
        const label = document.createElement("small");
        label.textContent = `${Math.ceil(remaining / 1000)}s`;
        container.appendChild(button);
        container.appendChild(timer);
        container.appendChild(label);
        return container;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "remove-button";
    button.textContent = "x";
    button.title = "Remove row";
    button.disabled = row.status === "Submitted" || Boolean(state.pendingBulkDelete);
    button.addEventListener("click", () => startDeleteCountdown(row));
    container.appendChild(button);
    return container;
}

function renderActiveRows() {
    const filteredRows = getFilteredActiveRows();
    const pageRows = getPagedRows(filteredRows, state.activePage);
    elements.activeBody.innerHTML = "";

    pageRows.forEach((row) => {
        const tr = document.createElement("tr");
        if (!row.is_temp) {
            tr.dataset.rowId = String(row.row_id ?? "");
            tr.dataset.fileName = row.file_name;
            tr.dataset.caseId = row.case_id || "";
            tr.dataset.rowStatus = getRowStatus(row);
        }
        if (isRowPendingDelete(row)) {
            tr.classList.add("row-pending-delete");
        }

        const selectCell = document.createElement("td");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.dataset.testid = "row-select";
        checkbox.checked = !row.is_temp && state.selectedIds.has(row.row_id);
        checkbox.disabled = !isEditableActiveRow(row);
        checkbox.addEventListener("change", (event) => toggleRowSelection(row, event.target.checked));
        selectCell.appendChild(checkbox);
        tr.appendChild(selectCell);

        const previewCell = document.createElement("td");
        previewCell.appendChild(createThumbnail(row));
        tr.appendChild(previewCell);

        const fileCell = document.createElement("td");
        const fileName = document.createElement("div");
        fileName.className = "file-name";
        fileName.textContent = row.file_name;
        fileCell.appendChild(fileName);
        tr.appendChild(fileCell);

        const caseCell = document.createElement("td");
        caseCell.textContent = row.case_id || "Missing";
        tr.appendChild(caseCell);

        const modelCell = document.createElement("td");
        modelCell.appendChild(createModelTypeSelect(row));
        tr.appendChild(modelCell);

        const presetCell = document.createElement("td");
        presetCell.appendChild(createPresetSelect(row));
        tr.appendChild(presetCell);

        const statusCell = document.createElement("td");
        const chip = createChip(rowStatusLabel(row));
        chip.dataset.testid = "status-chip";
        statusCell.appendChild(chip);
        tr.appendChild(statusCell);

        const dimensionsCell = document.createElement("td");
        dimensionsCell.textContent = formatDimensions(row.dimensions);
        tr.appendChild(dimensionsCell);

        const volumeCell = document.createElement("td");
        volumeCell.textContent = formatVolume(row);
        tr.appendChild(volumeCell);

        const removeCell = document.createElement("td");
        removeCell.appendChild(createRemoveCell(row));
        tr.appendChild(removeCell);

        elements.activeBody.appendChild(tr);
    });

    if (pageRows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 10;
        td.className = "table-empty";
        td.textContent = "No files currently need attention.";
        tr.appendChild(td);
        elements.activeBody.appendChild(tr);
    }

    const info = buildPageSelectionInfo(pageRows, filteredRows);
    elements.selectPageCheckbox.checked = info.rowIds.length > 0 && info.rowIds.every((rowId) => state.selectedIds.has(rowId));
    elements.selectPageCheckbox.disabled = info.rowIds.length === 0;
}

function renderWorkQueueSections() {
    renderActiveRows();

    const rows = getInProgressRows();
    elements.inProgressBody.innerHTML = "";

    rows.forEach((row) => {
        const tr = document.createElement("tr");

        const previewCell = document.createElement("td");
        previewCell.appendChild(createThumbnail(row));
        tr.appendChild(previewCell);

        const fileCell = document.createElement("td");
        const fileName = document.createElement("div");
        fileName.className = "file-name";
        fileName.textContent = row.file_name;
        fileCell.appendChild(fileName);
        tr.appendChild(fileCell);

        const caseCell = document.createElement("td");
        caseCell.textContent = row.case_id || "Missing";
        tr.appendChild(caseCell);

        const modelCell = document.createElement("td");
        modelCell.textContent = row.model_type || "-";
        tr.appendChild(modelCell);

        const presetCell = document.createElement("td");
        presetCell.textContent = row.preset || "-";
        tr.appendChild(presetCell);

        const statusCell = document.createElement("td");
        const chip = createChip(rowStatusLabel(row));
        chip.dataset.testid = "status-chip";
        statusCell.appendChild(chip);
        tr.appendChild(statusCell);

        const dimensionsCell = document.createElement("td");
        dimensionsCell.textContent = formatDimensions(row.dimensions);
        tr.appendChild(dimensionsCell);

        const volumeCell = document.createElement("td");
        volumeCell.textContent = formatVolume(row);
        tr.appendChild(volumeCell);

        elements.inProgressBody.appendChild(tr);
    });

    if (rows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 8;
        td.className = "table-empty";
        td.textContent = "No files are currently being processed.";
        tr.appendChild(td);
        elements.inProgressBody.appendChild(tr);
    }
}

function openHistoryJobLink(row) {
    if (!row.linked_job_name) {
        return;
    }
    state.activeTab = "print-queue";
    const job = state.printQueue.jobs.find((item) => item.job_name === row.linked_job_name);
    state.printQueue.highlightedJobId = job?.id || null;
    render();
}

function renderHistoryRows() {
    const pageRows = getPagedRows(state.processedRows, state.processedPage);
    elements.historyBody.innerHTML = "";

    pageRows.forEach((row) => {
        const tr = document.createElement("tr");
        const statusCell = document.createElement("td");
        statusCell.appendChild(createChip(rowStatusLabel(row)));
        tr.appendChild(statusCell);

        const fileCell = document.createElement("td");
        fileCell.className = "file-name";
        fileCell.textContent = row.file_name;
        tr.appendChild(fileCell);

        const caseCell = document.createElement("td");
        caseCell.textContent = row.case_id || "Missing";
        tr.appendChild(caseCell);

        const modelCell = document.createElement("td");
        modelCell.textContent = row.model_type || "-";
        tr.appendChild(modelCell);

        const presetCell = document.createElement("td");
        presetCell.textContent = row.preset || "-";
        tr.appendChild(presetCell);

        const jobCell = document.createElement("td");
        if (row.linked_job_name) {
            const linkButton = document.createElement("button");
            linkButton.type = "button";
            linkButton.className = "history-job-link";
            linkButton.textContent = row.linked_job_name;
            linkButton.addEventListener("click", () => openHistoryJobLink(row));
            jobCell.appendChild(linkButton);
        } else {
            jobCell.textContent = "-";
        }
        tr.appendChild(jobCell);

        const volumeCell = document.createElement("td");
        volumeCell.textContent = formatVolume(row);
        tr.appendChild(volumeCell);

        const printerCell = document.createElement("td");
        printerCell.textContent = row.printer || "-";
        tr.appendChild(printerCell);

        const dateCell = document.createElement("td");
        dateCell.textContent = formatDate(row.current_event_at);
        tr.appendChild(dateCell);

        const personCell = document.createElement("td");
        personCell.textContent = row.person || "-";
        tr.appendChild(personCell);

        elements.historyBody.appendChild(tr);
    });

    if (pageRows.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 10;
        td.className = "table-empty";
        td.textContent = "No history rows yet.";
        tr.appendChild(td);
        elements.historyBody.appendChild(tr);
    }
}

function createJobStatusChip(status) {
    const span = document.createElement("span");
    const safeClass = status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    span.className = `status-chip job-status-${safeClass}`;
    span.textContent = status;
    return span;
}

function createJobDetailItem(label, value) {
    const item = document.createElement("div");
    item.className = "job-detail-item";

    const labelSpan = document.createElement("span");
    labelSpan.className = "job-detail-label";
    labelSpan.textContent = label;
    item.appendChild(labelSpan);

    const valueSpan = document.createElement("span");
    valueSpan.className = "job-detail-value";
    valueSpan.textContent = value || "-";
    item.appendChild(document.createTextNode(" "));
    item.appendChild(valueSpan);

    return item;
}

async function releaseHeldJob(job, button) {
    button.disabled = true;
    setStatus(`Releasing ${job.job_name}...`);
    try {
        const response = await fetch(`/api/print-queue/jobs/${job.id}/release-now`, {
            method: "POST",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || "Could not release held build.");
        }
        await loadPrintQueue();
        await loadQueue();
        render();
        setStatus(`${job.job_name} released to print.`);
    } catch (error) {
        button.disabled = false;
        setStatus(error.message, true);
    }
}

function createReleaseButton(job) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button job-release-button";
    button.textContent = "Release now";
    button.addEventListener("click", () => releaseHeldJob(job, button));
    return button;
}

function createPrintQueueRow(job) {
    const tr = document.createElement("tr");
    tr.dataset.jobId = String(job.id);
    if (state.printQueue.highlightedJobId === job.id) {
        tr.classList.add("print-job-row-highlight");
    }

    const previewCell = document.createElement("td");
    const screenshotButton = document.createElement("button");
    screenshotButton.type = "button";
    screenshotButton.className = "job-screenshot-button";

    if (job.screenshot_url) {
        screenshotButton.addEventListener("click", () => openScreenshotModal(job));
        const img = document.createElement("img");
        img.src = job.screenshot_url;
        img.alt = `${job.job_name} screenshot`;
        img.loading = "lazy";
        screenshotButton.appendChild(img);
    } else {
        screenshotButton.disabled = true;
        const placeholder = document.createElement("div");
        placeholder.className = "job-screenshot-placeholder";
        placeholder.textContent = "Generating preview";
        screenshotButton.appendChild(placeholder);
    }

    previewCell.appendChild(screenshotButton);
    tr.appendChild(previewCell);

    const jobCell = document.createElement("td");
    const nameDiv = document.createElement("div");
    nameDiv.className = "file-name";
    nameDiv.textContent = job.job_name;
    const presetDiv = document.createElement("div");
    presetDiv.className = "file-meta";
    presetDiv.textContent = (job.preset_names || []).length > 0 ? job.preset_names.join(", ") : job.preset;
    jobCell.appendChild(nameDiv);
    jobCell.appendChild(presetDiv);
    tr.appendChild(jobCell);

    const casesCell = document.createElement("td");
    casesCell.textContent = (job.case_ids || []).length > 0 ? job.case_ids.join(", ") : "-";
    tr.appendChild(casesCell);

    const statusCell = document.createElement("td");
    statusCell.appendChild(createJobStatusChip(job.status));
    if (job.status === "Holding for More Cases") {
        statusCell.appendChild(createReleaseButton(job));
    }
    tr.appendChild(statusCell);

    const detailsCell = document.createElement("td");
    detailsCell.textContent = [
        job.printer_type || "-",
        job.resin || "-",
        job.layer_height_microns ? `${job.layer_height_microns} um` : "-",
    ].join(" | ");
    tr.appendChild(detailsCell);

    return tr;
}

function createJobCard(job) {
    const card = document.createElement("div");
    card.className = "job-card";
    card.dataset.jobId = job.id;
    if (state.printQueue.highlightedJobId === job.id) {
        card.classList.add("job-card-highlight");
    }
    card.tabIndex = -1;

    // Screenshot thumbnail
    const screenshotDiv = document.createElement("div");
    screenshotDiv.className = "job-screenshot";
    const screenshotButton = document.createElement("button");
    screenshotButton.type = "button";
    screenshotButton.className = "job-screenshot-button";
    screenshotButton.addEventListener("click", () => openScreenshotModal(job));
    
    if (job.screenshot_url) {
        const img = document.createElement("img");
        img.src = job.screenshot_url;
        img.alt = `${job.job_name} screenshot`;
        img.loading = "lazy";
        screenshotButton.appendChild(img);
    } else {
        const placeholder = document.createElement("div");
        placeholder.className = "job-screenshot-placeholder";
        placeholder.textContent = "No Preview";
        screenshotButton.appendChild(placeholder);
    }
    screenshotDiv.appendChild(screenshotButton);
    card.appendChild(screenshotDiv);

    // Job info section
    const infoDiv = document.createElement("div");
    infoDiv.className = "job-info";

    // Job name header
    const headerDiv = document.createElement("div");
    headerDiv.className = "job-header";
    const jobName = document.createElement("h3");
    jobName.className = "job-name";
    jobName.textContent = job.job_name;
    headerDiv.appendChild(jobName);
    headerDiv.appendChild(createJobStatusChip(job.status));
    if (job.status === "Holding for More Cases") {
        headerDiv.appendChild(createReleaseButton(job));
    }
    infoDiv.appendChild(headerDiv);

    // Cases list (expandable)
    if (job.case_ids && job.case_ids.length > 0) {
        const casesDiv = document.createElement("div");
        casesDiv.className = "job-cases";
        const casesHeader = document.createElement("button");
        casesHeader.type = "button";
        casesHeader.className = "job-cases-toggle";
        const isExpanded = state.printQueue.expandedCases.has(job.id);
        casesHeader.textContent = isExpanded ? `Hide Cases (${job.case_ids.length})` : `Show Cases (${job.case_ids.length})`;
        casesHeader.addEventListener("click", () => {
            if (state.printQueue.expandedCases.has(job.id)) {
                state.printQueue.expandedCases.delete(job.id);
            } else {
                state.printQueue.expandedCases.add(job.id);
            }
            renderPrintQueueJobs();
        });
        casesDiv.appendChild(casesHeader);

        if (isExpanded) {
            const casesList = document.createElement("ul");
            casesList.className = "job-cases-list";
            job.case_ids.forEach((caseId) => {
                const li = document.createElement("li");
                li.textContent = caseId;
                casesList.appendChild(li);
            });
            casesDiv.appendChild(casesList);
        }
        infoDiv.appendChild(casesDiv);
    }

    // Job details
    const detailsDiv = document.createElement("div");
    detailsDiv.className = "job-details";

    const presetList = (job.preset_names || []).length > 0
        ? job.preset_names.join(", ")
        : job.preset;
    detailsDiv.appendChild(createJobDetailItem("Presets:", presetList));
    detailsDiv.appendChild(createJobDetailItem("Build Profile:", job.compatibility_key));
    if (job.estimated_density != null) {
        detailsDiv.appendChild(createJobDetailItem("Density:", `${Math.round(job.estimated_density * 100)}%`));
    }
    if (job.hold_cutoff_at) {
        detailsDiv.appendChild(createJobDetailItem("Cutoff:", formatDate(job.hold_cutoff_at)));
    }

    const printerDiv = document.createElement("div");
    printerDiv.className = "job-detail-item";
    printerDiv.innerHTML = `<span class="job-detail-label">Printer:</span> <span class="job-detail-value">${job.printer_type || "-"}</span>`;
    detailsDiv.appendChild(printerDiv);

    const resinDiv = document.createElement("div");
    resinDiv.className = "job-detail-item";
    resinDiv.innerHTML = `<span class="job-detail-label">Resin:</span> <span class="job-detail-value">${job.resin || "-"}</span>`;
    detailsDiv.appendChild(resinDiv);

    const layerDiv = document.createElement("div");
    layerDiv.className = "job-detail-item";
    const layerHeight = job.layer_height_microns ? `${job.layer_height_microns}μm` : "-";
    layerDiv.innerHTML = `<span class="job-detail-label">Layer:</span> <span class="job-detail-value">${layerHeight}</span>`;
    detailsDiv.appendChild(layerDiv);

    infoDiv.appendChild(detailsDiv);
    card.appendChild(infoDiv);

    return card;
}

function renderPrintQueueJobs() {
    const pageJobs = getPagedRows(state.printQueue.jobs, state.printQueue.page);
    elements.printQueueBody.innerHTML = "";

    if (pageJobs.length === 0) {
        elements.printQueueEmpty.classList.remove("hidden");
        return;
    }

    elements.printQueueEmpty.classList.add("hidden");
    pageJobs.forEach((job) => {
        elements.printQueueBody.appendChild(createPrintQueueRow(job));
    });

    if (state.activeTab === "print-queue" && state.printQueue.highlightedJobId !== null) {
        const highlightedRow = elements.printQueueBody.querySelector(".print-job-row-highlight");
        if (highlightedRow) {
            window.requestAnimationFrame(() => {
                highlightedRow.scrollIntoView({ block: "center", behavior: "smooth" });
            });
        }
    }
}

function findNewestPrintJob(previousJobIds) {
    return state.printQueue.jobs.find((job) => !previousJobIds.has(job.id))
        || state.printQueue.jobs[0]
        || null;
}

function markRowsInProgress(rows, stage = "Processing") {
    const rowIds = new Set(rows.map((row) => row.row_id));
    state.activeRows = state.activeRows.map((row) => {
        if (!rowIds.has(row.row_id)) {
            return row;
        }
        const nextStage = row.volume_ml == null ? "Calculating Volume" : stage;
        return {
            ...row,
            queue_section: "in_progress",
            handoff_stage: nextStage,
        };
    });
}

function brieflyQueueRows(rows) {
    rows.forEach((row) => {
        state.transientQueuedRows.set(row.row_id, {
            ...row,
            queue_section: "in_progress",
            handoff_stage: "Queued",
        });
        window.setTimeout(() => {
            state.transientQueuedRows.delete(row.row_id);
            render();
        }, 2500);
    });
}

function describePrintReceipt(job, submittedCount) {
    if (!job) {
        return `Moved ${submittedCount} file(s) into In Progress.`;
    }

    const caseSummary = (job.case_ids || []).length > 0
        ? ` for ${job.case_ids.join(", ")}`
        : "";
    return `Moved ${submittedCount} file(s) into In Progress. Job ${job.job_name}${caseSummary} is available in Print Queue.`;
}

function openScreenshotModal(job) {
    elements.screenshotModal.classList.remove("hidden");
    elements.screenshotModal.setAttribute("aria-hidden", "false");
    elements.screenshotTitle.textContent = job.job_name;
    
    if (job.screenshot_url) {
        elements.screenshotImage.src = job.screenshot_url;
        elements.screenshotImage.alt = `${job.job_name} screenshot`;
        elements.screenshotCaption.textContent = `${job.printer_type || "-"} | ${job.resin || "-"} | ${job.layer_height_microns ? `${job.layer_height_microns}μm` : "-"}`;
    } else {
        elements.screenshotImage.src = "";
        elements.screenshotImage.alt = "No screenshot available";
        elements.screenshotCaption.textContent = "No screenshot available for this job.";
    }
}

function closeScreenshotModal() {
    elements.screenshotModal.classList.add("hidden");
    elements.screenshotModal.setAttribute("aria-hidden", "true");
    elements.screenshotImage.src = "";
}

function renderLegend() {
    elements.statusLegend.innerHTML = "";
    ACTIVE_STATUSES.forEach((status) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "legend-item";
        if (state.activeFilters.has(status)) {
            button.classList.add("legend-item-active");
        }
        button.appendChild(createChip(status));
        button.addEventListener("click", () => {
            if (state.activeFilters.has(status)) {
                state.activeFilters.delete(status);
            } else {
                state.activeFilters.add(status);
            }
            state.activePage = 1;
            render();
        });
        elements.statusLegend.appendChild(button);
    });
}

function renderBulkActions() {
    elements.bulkActions.innerHTML = "";
    if (state.pendingBulkDelete) {
        const summary = document.createElement("span");
        summary.className = "selection-summary";
        summary.textContent = `${state.pendingBulkDelete.rowIds.size} row(s) pending delete`;
        elements.bulkActions.appendChild(summary);

        const undoButton = document.createElement("button");
        undoButton.type = "button";
        undoButton.className = "secondary-button";
        undoButton.textContent = "Undo Delete";
        undoButton.addEventListener("click", () => undoBulkDelete());
        elements.bulkActions.appendChild(undoButton);

        const timer = document.createElement("div");
        timer.className = "bulk-undo";
        const remaining = Math.max(0, state.pendingBulkDelete.expiresAt - Date.now());
        const bar = document.createElement("span");
        bar.style.width = `${(remaining / DELETE_UNDO_MS) * 100}%`;
        timer.appendChild(bar);
        elements.bulkActions.appendChild(timer);

        const countdown = document.createElement("span");
        countdown.className = "selection-summary";
        countdown.textContent = `${Math.ceil(remaining / 1000)}s`;
        elements.bulkActions.appendChild(countdown);
        return;
    }

    const selectedRows = getSelectedRows();
    if (selectedRows.length === 0) {
        const hint = document.createElement("p");
        hint.className = "bulk-hint";
        hint.textContent = "Select editable rows for bulk updates, deletes, duplicate approval, or print submission.";
        elements.bulkActions.appendChild(hint);
        return;
    }

    const summary = document.createElement("span");
    summary.className = "selection-summary";
    summary.textContent = `${selectedRows.length} selected`;
    elements.bulkActions.appendChild(summary);

    const readyRows = selectedRows.filter(isReadyForPrint);
    const duplicateRows = selectedRows.filter(isDuplicateActionable);

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "ghost-button";
    deleteButton.textContent = `Delete (${selectedRows.length})`;
    deleteButton.addEventListener("click", () => startBulkDelete(selectedRows));
    elements.bulkActions.appendChild(deleteButton);

    const modelSelect = document.createElement("select");
    modelSelect.className = "bulk-select";
    modelSelect.setAttribute("aria-label", "Change Model Type");
    modelSelect.dataset.testid = "bulk-model-type-select";
    const modelPlaceholder = document.createElement("option");
    modelPlaceholder.value = "";
    modelPlaceholder.textContent = "Change Model Type";
    modelPlaceholder.disabled = true;
    modelPlaceholder.selected = !state.bulkModelTypeValue;
    modelSelect.appendChild(modelPlaceholder);
    MODEL_TYPES.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = state.bulkModelTypeValue === optionValue;
        modelSelect.appendChild(option);
    });
    modelSelect.addEventListener("change", async (event) => {
        const modelType = event.target.value;
        const rows = getSelectedRows();
        if (!modelType || rows.length === 0) {
            return;
        }
        state.bulkModelTypeValue = modelType;
        modelSelect.disabled = true;
        await applyBulkUpdate({
            row_ids: getRowIds(rows),
            model_type: modelType,
        }, `Updated model type for ${rows.length} row(s).`, () => {
            state.bulkModelTypeValue = "";
        });
    });
    elements.bulkActions.appendChild(modelSelect);

    const presetSelect = document.createElement("select");
    presetSelect.className = "bulk-select";
    presetSelect.setAttribute("aria-label", "Change Preset");
    presetSelect.dataset.testid = "bulk-preset-select";
    const presetPlaceholder = document.createElement("option");
    presetPlaceholder.value = "";
    presetPlaceholder.textContent = "Change Preset";
    presetPlaceholder.disabled = true;
    presetPlaceholder.selected = !state.bulkPresetValue;
    presetSelect.appendChild(presetPlaceholder);
    PRESET_OPTIONS.forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = state.bulkPresetValue === optionValue;
        presetSelect.appendChild(option);
    });
    presetSelect.addEventListener("change", async (event) => {
        const preset = event.target.value;
        const rows = getSelectedRows();
        if (!preset || rows.length === 0) {
            return;
        }
        state.bulkPresetValue = preset;
        presetSelect.disabled = true;
        await applyBulkUpdate({
            row_ids: getRowIds(rows),
            preset,
        }, `Updated preset for ${rows.length} row(s).`, () => {
            state.bulkPresetValue = "";
        });
    });
    elements.bulkActions.appendChild(presetSelect);

    if (duplicateRows.length > 0) {
        const allowButton = document.createElement("button");
        allowButton.type = "button";
        allowButton.className = "secondary-button";
        allowButton.textContent = `Allow Duplicate (${duplicateRows.length})`;
        allowButton.addEventListener("click", async (event) => {
            const rows = getSelectedRows().filter(isDuplicateActionable);
            if (rows.length === 0) {
                render();
                return;
            }
            event.currentTarget.disabled = true;
            await postRowsAction(
                "/api/uploads/rows/allow-duplicate",
                rows,
                `Allowed ${rows.length} duplicate row(s).`,
                "Could not allow duplicates."
            );
        });
        elements.bulkActions.appendChild(allowButton);
    }

    if (readyRows.length > 0) {
        const submitButton = document.createElement("button");
        submitButton.type = "button";
        submitButton.dataset.testid = "send-to-print-button";
        submitButton.className = canPrint() ? "primary-button" : "secondary-button";
        submitButton.textContent = canPrint()
            ? `Send to Print (${readyRows.length})`
            : `Setup Required (${readyRows.length})`;
        submitButton.addEventListener("click", async (event) => {
            if (!canPrint()) {
                openPreformWizard();
                setStatus("Complete PreFormServer setup before sending rows to print.", true);
                return;
            }
            const rows = getSelectedRows().filter(isReadyForPrint);
            if (rows.length === 0) {
                render();
                return;
            }
            event.currentTarget.disabled = true;
            await sendRowsToPrint(rows);
        });
        elements.bulkActions.appendChild(submitButton);
    }

    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "ghost-button";
    clearButton.textContent = "Clear Selection";
    clearButton.addEventListener("click", () => {
        state.selectedIds.clear();
        render();
    });
    elements.bulkActions.appendChild(clearButton);
}

function renderPagination(container, totalRows, currentPage, setPage) {
    container.innerHTML = "";
    const pageCount = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
    const summary = document.createElement("span");
    summary.className = "pagination-summary";
    summary.textContent = `Page ${currentPage} of ${pageCount}`;

    const prevButton = document.createElement("button");
    prevButton.type = "button";
    prevButton.className = "ghost-button";
    prevButton.textContent = "Previous";
    prevButton.disabled = currentPage === 1;
    prevButton.addEventListener("click", () => {
        setPage(currentPage - 1);
        render();
    });

    const nextButton = document.createElement("button");
    nextButton.type = "button";
    nextButton.className = "ghost-button";
    nextButton.textContent = "Next";
    nextButton.disabled = currentPage >= pageCount;
    nextButton.addEventListener("click", () => {
        setPage(currentPage + 1);
        render();
    });

    container.appendChild(summary);
    container.appendChild(prevButton);
    container.appendChild(nextButton);
}

function renderTabs() {
    const workQueueCount = state.activeRows.length + state.pendingRows.length;
    elements.workQueueCount.textContent = workQueueCount;
    elements.historyCount.textContent = state.processedRows.length;
    elements.printQueueCount.textContent = state.printQueue.jobs.length;

    const showEmpty = workQueueCount === 0 && state.processedRows.length === 0 && state.printQueue.jobs.length === 0;
    elements.emptyState.classList.toggle("hidden", !showEmpty);
    elements.workQueuePanel.classList.toggle("hidden", showEmpty || state.activeTab !== "work-queue");
    elements.historyPanel.classList.toggle("hidden", showEmpty || state.activeTab !== "history");
    elements.printQueuePanel.classList.toggle("hidden", showEmpty || state.activeTab !== "print-queue");
    elements.workQueueTab.classList.toggle("tab-button-active", state.activeTab === "work-queue");
    elements.historyTab.classList.toggle("tab-button-active", state.activeTab === "history");
    elements.printQueueTab.classList.toggle("tab-button-active", state.activeTab === "print-queue");
    elements.workQueueTab.setAttribute("aria-selected", String(state.activeTab === "work-queue"));
    elements.historyTab.setAttribute("aria-selected", String(state.activeTab === "history"));
    elements.printQueueTab.setAttribute("aria-selected", String(state.activeTab === "print-queue"));
}

function render() {
    clampPages();
    syncSelection();
    renderPreformSetup();
    renderTabs();
    renderLegend();
    renderBulkActions();
    renderWorkQueueSections();
    renderHistoryRows();
    renderPrintQueueJobs();
    renderPagination(elements.activePaginationTop, getFilteredActiveRows().length, state.activePage, (page) => {
        state.activePage = page;
    });
    renderPagination(elements.activePaginationBottom, getFilteredActiveRows().length, state.activePage, (page) => {
        state.activePage = page;
    });
    renderPagination(elements.historyPaginationTop, state.processedRows.length, state.processedPage, (page) => {
        state.processedPage = page;
    });
    renderPagination(elements.historyPaginationBottom, state.processedRows.length, state.processedPage, (page) => {
        state.processedPage = page;
    });
    renderPagination(elements.printQueuePaginationTop, state.printQueue.jobs.length, state.printQueue.page, (page) => {
        state.printQueue.page = page;
    });
    renderPagination(elements.printQueuePaginationBottom, state.printQueue.jobs.length, state.printQueue.page, (page) => {
        state.printQueue.page = page;
    });
    elements.queueActionButton.textContent = "Select STL Files";
    elements.printQueueEmpty.textContent = canPrint()
        ? "No print jobs in queue."
        : "Print queue unavailable until PreFormServer setup is ready.";
}

function createPendingRow(file) {
    return {
        temp_id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        file_name: file.name,
        case_id: null,
        model_type: null,
        preset: null,
        confidence: "low",
        status: "Queued",
        dimensions: null,
        volume_ml: null,
        is_temp: true,
        file,
        preset_overridden: false,
        deleteRequested: false,
        abortController: null,
    };
}

function addPendingFiles(files) {
    const stlFiles = files.filter((file) => file.name.toLowerCase().endsWith(".stl"));
    if (stlFiles.length === 0) {
        setStatus("No STL files were found in that selection.", true);
        return;
    }

    stlFiles.forEach((file) => state.pendingRows.push(createPendingRow(file)));
    state.activeTab = "work-queue";
    setStatus(`Queued ${stlFiles.length} STL file(s) for upload.`);
    render();
    drainUploadQueue();
}

function removePendingRow(tempId) {
    state.pendingRows = state.pendingRows.filter((row) => row.temp_id !== tempId);
}

function startBulkDelete(rows) {
    if (state.pendingBulkDelete || rows.length === 0) {
        return;
    }

    const rowIds = new Set(rows.map((row) => row.row_id));
    const timeoutId = window.setTimeout(async () => {
        const pending = state.pendingBulkDelete;
        state.pendingBulkDelete = null;

        try {
            const response = await fetch("/api/uploads/rows/bulk-delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ row_ids: [...rowIds] }),
            });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.detail || "Could not delete rows.");
            }
            await fetchQueue();
            setStatus(`Removed ${payload.deleted_row_ids.length} row(s).`);
        } catch (error) {
            if (pending) {
                state.selectedIds = new Set([...pending.rowIds]);
            }
            setStatus(error.message, true);
        } finally {
            render();
        }
    }, DELETE_UNDO_MS);

    state.pendingBulkDelete = {
        rowIds,
        expiresAt: Date.now() + DELETE_UNDO_MS,
        timeoutId,
    };
    state.selectedIds.clear();
    render();
}

function undoBulkDelete() {
    if (!state.pendingBulkDelete) {
        return;
    }
    window.clearTimeout(state.pendingBulkDelete.timeoutId);
    state.selectedIds = new Set([...state.pendingBulkDelete.rowIds]);
    state.pendingBulkDelete = null;
    render();
}

async function readResponseJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return {};
    }
}

async function applyBulkUpdate(payload, successMessage, onSuccess = null) {
    try {
        const response = await fetch("/api/uploads/rows/bulk-update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await readResponseJson(response);
        if (!response.ok) {
            throw new Error(data.detail || "Could not update rows.");
        }
        await fetchQueue();
        if (onSuccess) {
            onSuccess();
        }
        setStatus(successMessage);
        render();
        return true;
    } catch (error) {
        setStatus(error.message, true);
        render();
        return false;
    }
}

async function postRowsAction(endpoint, rows, successMessage, fallbackMessage) {
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ row_ids: getRowIds(rows) }),
        });
        const payload = await readResponseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || fallbackMessage);
        }
        await fetchQueue();
        setStatus(successMessage);
        render();
        return true;
    } catch (error) {
        setStatus(error.message, true);
        render();
        return false;
    }
}

async function sendRowsToPrint(rows) {
    const previousJobIds = new Set(state.printQueue.jobs.map((job) => job.id));
    state.activeTab = "work-queue";
    markRowsInProgress(rows, "Processing");
    render();

    try {
        const response = await fetch("/api/uploads/rows/send-to-print", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ row_ids: getRowIds(rows) }),
        });
        const payload = await readResponseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Could not submit rows.");
        }

        await fetchQueue();
        await fetchPrintQueue();

        const newJob = findNewestPrintJob(previousJobIds);
        state.printQueue.highlightedJobId = newJob?.id || null;
        state.printQueue.page = 1;
        brieflyQueueRows(payload.filter((row) => row.status === "Submitted"));
        setStatus(describePrintReceipt(newJob, rows.length));
        render();
        return true;
    } catch (error) {
        setStatus(error.message, true);
        render();
        return false;
    }
}

async function uploadPendingRow(row) {
    row.status = "Uploading";
    row.abortController = new AbortController();
    state.inflightUploads += 1;
    render();

    const analyzeTimer = window.setTimeout(() => {
        if (row.status === "Uploading") {
            row.status = "Analyzing";
            render();
        }
    }, 450);

    try {
        const formData = new FormData();
        formData.append("files", row.file);
        const response = await fetch("/api/uploads/classify", {
            method: "POST",
            body: formData,
            signal: row.abortController.signal,
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || "Upload failed.");
        }

        if (payload.rows[0]) {
            state.activeRows.push(normalizeRow(payload.rows[0]));
            sortRows();
            setStatus(`Uploaded ${row.file_name}.`);
        }
        removePendingRow(row.temp_id);
    } catch (error) {
        if (error.name === "AbortError") {
            removePendingRow(row.temp_id);
        } else {
            row.status = "Needs Review";
            row.error_message = error.message;
            setStatus(error.message, true);
        }
    } finally {
        window.clearTimeout(analyzeTimer);
        state.inflightUploads = Math.max(0, state.inflightUploads - 1);
        row.abortController = null;
        render();
        drainUploadQueue();
    }
}

function drainUploadQueue() {
    while (state.inflightUploads < MAX_CONCURRENT_UPLOADS) {
        const nextRow = state.pendingRows.find((row) => row.status === "Queued" && !state.pendingDeletes.has(getRowKey(row)));
        if (!nextRow) {
            break;
        }
        uploadPendingRow(nextRow);
    }
}

function readEntries(reader) {
    return new Promise((resolve) => {
        const entries = [];
        function pump() {
            reader.readEntries((results) => {
                if (!results.length) {
                    resolve(entries);
                    return;
                }
                entries.push(...results);
                pump();
            });
        }
        pump();
    });
}

async function collectEntryFiles(entry) {
    if (entry.isFile) {
        return new Promise((resolve) => entry.file((file) => resolve([file])));
    }
    if (!entry.isDirectory) {
        return [];
    }
    const reader = entry.createReader();
    const entries = await readEntries(reader);
    const nested = await Promise.all(entries.map((child) => collectEntryFiles(child)));
    return nested.flat();
}

async function extractDroppedFiles(event) {
    const items = Array.from(event.dataTransfer.items || []);
    if (items.length === 0 || !items[0].webkitGetAsEntry) {
        return Array.from(event.dataTransfer.files || []);
    }
    const fileSets = await Promise.all(
        items
            .filter((item) => item.kind === "file")
            .map((item) => collectEntryFiles(item.webkitGetAsEntry()))
    );
    return fileSets.flat();
}

async function openPreview(row) {
    closePreview();
    elements.previewModal.classList.remove("hidden");
    elements.previewModal.setAttribute("aria-hidden", "false");
    elements.previewTitle.textContent = row.file_name;
    elements.previewCaption.textContent = row.is_temp
        ? `${row.status} | local file preview`
        : `${formatDimensions(row.dimensions)} | ${formatVolume(row)}`;

    if (row.is_temp && !row.file) {
        const placeholder = document.createElement("div");
        placeholder.className = "preview-empty";
        placeholder.textContent = "Preview opens after upload completes.";
        elements.previewViewer.appendChild(placeholder);
        return;
    }

    let previewDeps;
    try {
        previewDeps = await ensurePreviewDependencies();
    } catch (error) {
        const placeholder = document.createElement("div");
        placeholder.className = "preview-empty";
        placeholder.textContent = "3D viewer dependency did not load.";
        elements.previewViewer.appendChild(placeholder);
        return;
    }

    const { THREE, STLLoader } = previewDeps;

    const width = elements.previewViewer.clientWidth || 820;
    const height = elements.previewViewer.clientHeight || 520;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(width, height);
    elements.previewViewer.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf7f3ec);
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 5000);
    camera.position.set(0, 0, 180);
    scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const directional = new THREE.DirectionalLight(0xffffff, 1.5);
    directional.position.set(50, 70, 120);
    scene.add(directional);

    const group = new THREE.Group();
    scene.add(group);
    const loader = new STLLoader();
    try {
        const buffer = await loadStlBuffer(row);
        const geometry = loader.parse(buffer);
        geometry.computeBoundingBox();
        geometry.center();
        geometry.computeVertexNormals();

        const material = new THREE.MeshStandardMaterial({
            color: 0xff7a2b,
            metalness: 0.12,
            roughness: 0.55,
        });
        const mesh = new THREE.Mesh(geometry, material);
        group.add(mesh);

        const bounds = geometry.boundingBox;
        const size = new THREE.Vector3();
        bounds.getSize(size);
        const maxDimension = Math.max(size.x, size.y, size.z) || 1;
        camera.position.set(0, maxDimension * 0.2, maxDimension * 2.2);
        camera.lookAt(0, 0, 0);

        let dragging = false;
        let lastX = 0;
        let lastY = 0;
        const canvas = renderer.domElement;
        canvas.addEventListener("pointerdown", (event) => {
            dragging = true;
            lastX = event.clientX;
            lastY = event.clientY;
            canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener("pointermove", (event) => {
            if (!dragging) {
                return;
            }
            group.rotation.y += (event.clientX - lastX) * 0.01;
            group.rotation.x += (event.clientY - lastY) * 0.01;
            lastX = event.clientX;
            lastY = event.clientY;
        });
        canvas.addEventListener("pointerup", (event) => {
            dragging = false;
            canvas.releasePointerCapture(event.pointerId);
        });
        canvas.addEventListener("wheel", (event) => {
            event.preventDefault();
            camera.position.z = Math.max(maxDimension * 0.8, Math.min(maxDimension * 5, camera.position.z + event.deltaY * 0.02));
        });

        const animate = () => {
            renderer.render(scene, camera);
            state.preview.frameId = window.requestAnimationFrame(animate);
        };
        animate();

        state.preview.renderer = renderer;
        state.preview.cleanup = () => {
            geometry.dispose();
            material.dispose();
            renderer.dispose();
        };
    } catch (error) {
        renderer.dispose();
        elements.previewViewer.innerHTML = "";
        const placeholder = document.createElement("div");
        placeholder.className = "preview-empty";
        placeholder.textContent = "Preview could not be loaded.";
        elements.previewViewer.appendChild(placeholder);
    }
}

function closePreview() {
    if (state.preview.frameId) {
        window.cancelAnimationFrame(state.preview.frameId);
    }
    if (state.preview.cleanup) {
        state.preview.cleanup();
    }
    state.preview.frameId = null;
    state.preview.cleanup = null;
    state.preview.renderer = null;
    elements.previewViewer.innerHTML = "";
    elements.previewModal.classList.add("hidden");
    elements.previewModal.setAttribute("aria-hidden", "true");
}

elements.workQueueTab.addEventListener("click", () => {
    state.activeTab = "work-queue";
    render();
});

elements.historyTab.addEventListener("click", () => {
    state.activeTab = "history";
    render();
});

elements.printQueueTab.addEventListener("click", () => {
    state.activeTab = "print-queue";
    render();
});

elements.queueActionButton.addEventListener("click", (event) => {
    event.stopPropagation();
    openPicker(elements.fileInput);
});

elements.dropzone.addEventListener("click", (event) => {
    openPicker(elements.fileInput);
});

elements.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPicker(elements.fileInput);
    }
});

elements.fileInput.addEventListener("change", (event) => {
    addPendingFiles(Array.from(event.target.files || []));
    event.target.value = "";
    releasePickerGuard();
});

window.addEventListener("focus", () => {
    if (state.pickerOpen) {
        schedulePickerGuardRelease();
    }
});

["dragenter", "dragover"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.dropzone.classList.add("dropzone-active");
    });
});

["dragleave", "drop"].forEach((eventName) => {
    elements.dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.dropzone.classList.remove("dropzone-active");
    });
});

elements.dropzone.addEventListener("drop", async (event) => {
    addPendingFiles(await extractDroppedFiles(event));
});

elements.selectPageCheckbox.addEventListener("change", (event) => {
    toggleSelectPage(event.target.checked);
});

elements.previewModal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") {
        closePreview();
    }
});

elements.closePreview.addEventListener("click", closePreview);

elements.screenshotModal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") {
        closeScreenshotModal();
    }
});

elements.closeScreenshot.addEventListener("click", closeScreenshotModal);

elements.preformInstallButton.addEventListener("click", () => {
    openPicker(elements.preformZipInput);
});

elements.preformZipInput.addEventListener("change", async (event) => {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    releasePickerGuard();
    if (!file) {
        return;
    }

    const formData = new FormData();
    formData.append("package", file, file.name);
    await runPreformAction("/api/preform-setup/install-from-zip", {
        method: "POST",
        body: formData,
    }, "PreFormServer installed.");
});

elements.preformStartButton.addEventListener("click", async () => {
    await runPreformAction("/api/preform-setup/start", { method: "POST" }, "PreFormServer start requested.");
});

elements.preformStopButton.addEventListener("click", async () => {
    await runPreformAction("/api/preform-setup/stop", { method: "POST" }, "PreFormServer stop requested.");
});

elements.preformRestartButton.addEventListener("click", async () => {
    await runPreformAction("/api/preform-setup/restart", { method: "POST" }, "PreFormServer restart requested.");
});

elements.preformRecheckButton.addEventListener("click", async () => {
    await runPreformAction("/api/preform-setup/recheck", { method: "POST" }, "PreFormServer readiness refreshed.");
});

elements.preformWizard.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "wizard" || event.target.dataset.wizardDismiss === "true") {
        dismissPreformWizard();
        return;
    }
    if (event.target.dataset.preformInstall === "true") {
        openPicker(elements.preformZipInput);
        return;
    }
    if (event.target.dataset.preformRecheck === "true") {
        runPreformAction("/api/preform-setup/recheck", { method: "POST" }, "PreFormServer readiness refreshed.");
    }
});


// Queue polling - auto-refresh every 10 seconds
window.pollingPaused = false;
window.pollInterval = 10000; // 10 seconds

window.setInterval(async () => {
    if (window.pollingPaused) return;
    try {
        await fetchQueue();
        await fetchPreformSetupStatus();
        render();
        console.log("Queue auto-refreshed");
    } catch (error) {
        console.error("Polling error:", error.message);
    }
}, window.pollInterval);

// Print queue polling - auto-refresh every 5 seconds
window.printQueuePollInterval = PRINT_QUEUE_POLL_INTERVAL;

window.setInterval(async () => {
    if (window.pollingPaused) return;
    try {
        await fetchPrintQueue();
        if (state.activeTab === "print-queue") {
            renderPrintQueueJobs();
            renderPagination(elements.printQueuePaginationTop, state.printQueue.jobs.length, state.printQueue.page, (page) => {
                state.printQueue.page = page;
            });
            renderPagination(elements.printQueuePaginationBottom, state.printQueue.jobs.length, state.printQueue.page, (page) => {
                state.printQueue.page = page;
            });
            elements.printQueueCount.textContent = state.printQueue.jobs.length;
        }
        console.log("Print queue auto-refreshed");
    } catch (error) {
        console.error("Print queue polling error:", error.message);
    }
}, window.printQueuePollInterval);

// Undo cleanup interval (500ms)
window.setInterval(() => {
    if (state.pendingDeletes.size > 0 || state.pendingBulkDelete) {
        render();
    }
}, 500);

async function bootstrap() {
    try {
        await fetchQueue();
        await fetchPrintQueue();
        await fetchPreformSetupStatus();
        render();
        if (canPrint()) {
            setStatus("Queue loaded.");
        } else {
            setStatus("Queue loaded. Complete PreFormServer setup before printing.", true);
        }
    } catch (error) {
        setStatus(error.message, true);
        render();
    }
}

bootstrap();
