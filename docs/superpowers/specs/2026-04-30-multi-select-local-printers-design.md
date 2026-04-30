# Multi-Select Local Printers for Send to Print

**Date:** 2026-04-30  
**Status:** Revised (v3)

---

## Context

Andent Web currently routes print jobs to one of two hardcoded printer *groups* ("Form 4BL" / "Form 4B"). This works for a single-printer lab but breaks down when a lab has multiple physical Formlabs printers of the same model — there is no way to target a specific machine. The operator also has no visibility into which device will receive a job before dispatching.

The goal is to replace the hardcoded printer group concept with live physical printer selection at the point of dispatch, via a "Send to Print" modal that shows detected devices and lets the operator assign each planned build manifest to a specific printer.

---

## Architecture

### Data Flow

1. Operator selects a **target printer model** (Form 4BL or Form 4B) for the batch — see [Printer Model Selection](#printer-model-selection) below.
2. Operator clicks **Send to Print (n)** in the bulk actions bar (only enabled when PreFormServer is reachable — existing `canPrint()` gate, unchanged).
3. Frontend calls `GET /api/preform-setup/devices` and `GET /api/uploads/rows/preview-batches?row_ids=…` in parallel.
4. Modal renders — one card per planned **BuildManifest**, each showing compatible physical devices in a dropdown.
5. Operator assigns a printer to each manifest group; clicks **Send All**.
6. Frontend calls `POST /api/uploads/rows/send-to-print` with `printer_assignments` keyed by `manifest_id` (stable, unique per manifest).
7. Backend re-plans from `row_ids`, validates each assignment matches the current manifest by exact `row_ids`, validates device model compatibility, then dispatches all-or-nothing.

### Key Design Decisions

- **BuildManifest is the stable unit of assignment** — the modal shows actual planned manifests (from `plan_build_manifests()`), not raw compatibility buckets.
- **`manifest_id` is unique and stable** — formed as `{compatibility_key}|{sorted_row_ids_hash}` (e.g. `form-4bl|precision-model-v1|100|a3f9c2`). The backend validates assignments by exact `row_ids` match, not just by key string.
- **Printer model selection drives planning** — `row.printer` (as printer group) continues to drive `plan_build_manifests()`. A model-level selector in the work queue UI writes to `row.printer` before the modal opens, preserving the existing planning path.
- **Device compatibility is server-enforced** — the backend resolves the selected device's model from `list_devices()` and verifies it matches the manifest's `printer_group`. Returns 422 if incompatible.
- **`__virtual__` bypasses model validation** — Virtual Printer is always accepted for any manifest model; it is routed to `_resolve_virtual_device_id` without model checking.
- **Explicit assignments bypass the global dispatch mode** — when `printer_assignments` is present, each manifest calls `send_to_printer()` directly regardless of `ANDENT_WEB_PRINT_DISPATCH_MODE`. Legacy calls without `printer_assignments` preserve existing mode behaviour.
- **All-or-nothing for v1** — validation failures return a 422 with a structured error body listing per-group reasons. On success, all groups are submitted and a 200 is returned listing all groups as `"submitted"`. There is no mixed success/failure 200.

---

## Printer Model Selection

`row.printer` (the existing printer group field, e.g. "Form 4BL") continues to drive `plan_build_manifests()` in `build_planning.py:69`. Removing the per-row printer dropdown without a replacement would lock all rows to their current `.printer` value (defaulting to "Form 4BL"), preventing an operator from routing cases to a Form 4B device.

**Solution:** Keep a **model-level selector** in the work queue UI. The existing bulk "Change Printer" dropdown (`renderBulkActions`, lines 2041–2073) is retained but its options change from `PRINTER_OPTIONS` to the live device models available from PreFormServer. This writes to `row.printer` as before, which continues to drive planning.

The per-row `createPrinterSelect()` dropdown is removed — model assignment is bulk-only. The printer cell in the work queue table becomes a read-only pill.

**Summary of UI control changes:**

| Control | Before | After |
|---|---|---|
| Per-row printer dropdown | Editable select (Form 4BL / Form 4B) | Read-only pill (last dispatched device name) |
| Bulk "Change Printer" | Form 4BL / Form 4B | Live device models from PreFormServer |
| Send to Print button | Calls API directly | Opens modal |

---

## New API Endpoints

### `GET /api/preform-setup/devices`

Added to `app/routers/preform_setup.py`. Aligns with the existing `/api/preform-setup/printers` contract shape.

Response:
```json
{
  "available": true,
  "message": null,
  "devices": [
    { "id": "abc-123", "name": "Lab Printer 1", "model": "Form 4BL", "status": "ready" },
    { "id": "def-456", "name": "Lab Printer 2", "model": "Form 4B",  "status": "busy"  }
  ]
}
```

- `available: false` + `message` when PreFormServer is unreachable — distinguishes "no printers" from "cannot discover printers."
- No caching — always live.
- Calls `preform_client.list_devices()`, normalises each device to `{ id, name, model, status }`.

### `GET /api/uploads/rows/preview-batches`

Added to `app/routers/uploads.py`.

- Query param: `row_ids` (comma-separated integers).
- Calls `plan_build_manifests(selected_rows)` from `app/services/build_planning.py` — the same planner used at dispatch time.
- Read-only — no side effects, safe to call multiple times.

Response:
```json
{
  "groups": [
    {
      "manifest_id": "form-4bl|precision-model-v1|100|a3f9c2",
      "row_ids": [1, 2, 3],
      "case_ids": ["Case-01", "Case-02", "Case-03"],
      "compatibility_key": "form-4bl|precision-model-v1|100",
      "printer_model": "Form 4BL",
      "material_label": "Precision Model V1",
      "layer_height_microns": 100,
      "planning_status": "planned",
      "non_plannable_reason": null
    }
  ]
}
```

- `planning_status`: uses existing `BuildPlanningStatus` enum — `"planned"` or `"non_plannable"` (`schemas.py:11`).
- `manifest_id` is `{compatibility_key}|{sha256(sorted(row_ids))[:6]}` — unique even when the same compatibility key produces multiple manifests (build plate overflow).
- Non-plannable groups are shown in the modal as disabled cards with `non_plannable_reason` displayed.

---

## Modified API Endpoints

### `POST /api/uploads/rows/send-to-print`

Request body gains an optional `printer_assignments` field:

```json
{
  "row_ids": [1, 2, 3, 4],
  "printer_assignments": [
    { "manifest_id": "form-4bl|precision-model-v1|100|a3f9c2", "device_id": "abc-123", "row_ids": [1, 2, 3] },
    { "manifest_id": "form-4b|lt-clear-v2|100|d7e1f4",         "device_id": "__virtual__", "row_ids": [4] }
  ]
}
```

- If `printer_assignments` is present: backend re-plans from `row_ids`, verifies each assignment's `row_ids` exactly matches a current manifest (stale detection), validates device model compatibility (except `__virtual__`), then dispatches all-or-nothing.
- `"__virtual__"` bypasses model validation and routes to `_resolve_virtual_device_id`.
- If `printer_assignments` is absent: existing behaviour unchanged (backwards compatible).

**Success response (HTTP 200):**
```json
{
  "groups": [
    { "manifest_id": "...", "status": "submitted", "row_ids": [1, 2, 3] },
    { "manifest_id": "...", "status": "submitted", "row_ids": [4] }
  ],
  "rows": [/* updated ClassificationRow list */]
}
```

**Failure response (HTTP 422):**
```json
{
  "groups": [
    { "manifest_id": "...", "status": "failed", "error": "Device model mismatch: selected Form 4B, manifest requires Form 4BL", "row_ids": [1, 2, 3] },
    { "manifest_id": "...", "status": "failed", "error": "Stale assignment: row_ids no longer match current plan", "row_ids": [4] }
  ]
}
```

No mixed success/failure response — either all groups are submitted (200) or all fail (422).

---

## Backend Changes

### `_resolve_device_id` — `app/services/print_queue_service.py`

When `device_id` is explicitly provided:
1. If `device_id == "__virtual__"` → route to `_resolve_virtual_device_id`, skip model validation.
2. Otherwise: call `list_devices()`, find device by id, extract `model`, verify it matches manifest `printer_group`. Raise `ValueError` with per-group error message if incompatible (caller converts to 422).

The existing fallback (infer from rows, default to "Form 4BL") is kept for calls without `printer_assignments`.

### Dispatch mode

Explicit `printer_assignments` bypass `ANDENT_WEB_PRINT_DISPATCH_MODE` — each manifest calls `send_to_printer()` directly. Legacy calls without `printer_assignments` continue to respect the global mode.

### `row.printer` field

Not reused for physical device identity. Continues to serve as printer group hint for `plan_build_manifests()`. The read-only pill in the work queue table shows `printer_type` from the most recent `PrintJob` for that row's case_id (not `row.printer`). No new device identity fields added in v1.

---

## Frontend Changes (`app/static/app.js`)

### Removed
- `PRINTER_OPTIONS` constant (line 20).
- `createPrinterSelect()` function (lines 1063–1097) — per-row printer dropdown.

### Modified
- Bulk "Change Printer" dropdown (`renderBulkActions`, lines 2041–2073) — options change from hardcoded `PRINTER_OPTIONS` to live device models fetched from `/api/preform-setup/devices` (distinct `model` values only, e.g. "Form 4BL", "Form 4B"). Writes to `row.printer` as before.
- `sendRowsToPrint(rows)` — opens the Send to Print modal instead of calling the API directly.
- Row rendering — printer cell shows a read-only text pill (last dispatched device name from PrintJob, or "—").

### Added: Send to Print Modal

Triggered by the existing "Send to Print" button. Lifecycle:

1. **Open** — fetch `/api/preform-setup/devices` and `/api/uploads/rows/preview-batches` in parallel.
2. **Render** — one card per planned manifest group:
   - Header: `{printer_model} · {material} · {layer_height}`
   - Sub-line: case IDs
   - Dropdown: real devices filtered to matching `printer_model` + always-present "Virtual Printer" at the bottom, separated by a divider
   - Non-plannable groups shown as disabled cards with reason text
3. **Printer dropdown options (per group):**
   - Real printers where `device.model === group.printer_model`: `● {name}  ({model}, {status})` — status dot (green = ready, amber = busy, red = offline); offline printers dimmed but selectable
   - Separator `─────`
   - `◌ Virtual Printer  (simulate)`
4. **Send All button** — disabled until every plannable group has a printer assigned.
5. **On Send All** — calls `POST /api/uploads/rows/send-to-print` with `printer_assignments`; on 200 closes modal and updates queue; on 422 shows per-group inline errors without closing modal.

### Modal HTML (`app/static/index.html`)

```
#send-to-print-modal
  .modal-header    "Send to Print"  [×]
  .modal-body      #stp-groups-container  (cards injected by JS)
  .modal-footer    [Cancel]  [Send All]
```

---

## Styles (`app/static/styles.css`)

- Modal overlay + card styles for `#send-to-print-modal`.
- Status dot variants: `.stp-status-ready`, `.stp-status-busy`, `.stp-status-offline`.
- Dimmed option style for offline printers.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| PreFormServer offline | "Send to Print" button disabled — existing `canPrint()` gate, no change |
| `available: false` from `/devices` | Modal cannot open (gate should have blocked this; defensive only) |
| No compatible devices for a group | Dropdown shows only "Virtual Printer"; real printer options absent |
| Device model mismatch at dispatch | 422 with per-group errors; no jobs dispatched |
| Stale assignment (row_ids no longer match plan) | 422 "stale assignment" per group; operator re-opens modal |
| Non-plannable group in preview | Card shown as disabled with reason; excluded from Send All |

---

## Files to Modify

| File | Change |
|---|---|
| `app/routers/preform_setup.py` | Add `GET /api/preform-setup/devices` |
| `app/routers/uploads.py` | Add `GET /api/uploads/rows/preview-batches`; update `send-to-print` request + response schema |
| `app/schemas.py` | Add `DeviceInfo`, `PreviewBatchGroup`, `PrinterAssignment`, `SendToPrintResponse` models; update `SendToPrintRequest` |
| `app/services/print_queue_service.py` | Update `send_ready_rows_to_print` + `_resolve_device_id` to accept explicit `device_id`; add device model validation |
| `app/services/build_planning.py` | Expose `plan_build_manifests()` for use by preview-batches endpoint; verify it is callable standalone |
| `app/static/index.html` | Add `#send-to-print-modal` markup |
| `app/static/app.js` | Remove `PRINTER_OPTIONS`, `createPrinterSelect`; update bulk model selector; add modal logic |
| `app/static/styles.css` | Add modal + status dot styles |

---

## Verification

1. Start app with PreFormServer offline — "Send to Print" button is disabled.
2. Start PreFormServer; click "Send to Print" — modal opens, planned manifest groups shown with unique `manifest_id`s, Virtual Printer present in all dropdowns.
3. Assign Virtual Printer to all groups; click "Send All" — 200 response, all groups `"submitted"`, work queue updates.
4. With two physical printers (different models) connected, use bulk model selector to set printer model, then assign each group to its compatible device — each manifest dispatched to correct device.
5. Attempt to assign a Form 4B device to a Form 4BL manifest — 422 with per-group error, no jobs dispatched, modal stays open showing inline error.
6. Change rows between modal open and Send All — 422 "stale assignment", modal prompts re-open.
7. Two manifests with same compatibility key (overflow) — each has a distinct `manifest_id`; assignments map correctly.
8. Call `POST /api/uploads/rows/send-to-print` without `printer_assignments` — existing behaviour unchanged.
