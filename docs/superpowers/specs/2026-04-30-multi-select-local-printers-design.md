# Multi-Select Local Printers for Send to Print

**Date:** 2026-04-30  
**Status:** Revised (v4)

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
6. Frontend calls `POST /api/uploads/rows/send-to-print` with `printer_assignments` keyed by `manifest_id`.
7. Backend re-plans from `row_ids`, validates each assignment matches the current manifest by exact `row_ids`, validates device model compatibility, then dispatches all-or-nothing.

### Key Design Decisions

- **BuildManifest is the stable unit of assignment** — the modal shows actual planned manifests (from `plan_build_manifests()`), not raw compatibility buckets.
- **`manifest_id` is unique and stable** — formed as `{compatibility_key}|{sha256(sorted(row_ids))[:6]}`. The backend validates assignments by exact `row_ids` match, not just key string. Two manifests with the same compatibility key (build plate overflow) get distinct IDs.
- **Printer model selection drives planning** — `row.printer` (as printer group) continues to drive `plan_build_manifests()`. A model-level bulk selector in the UI writes to `row.printer` before the modal opens.
- **`_dispatch_scene_if_enabled` and `process_print_manifest` accept an explicit `device_id`** — when `printer_assignments` is present, `process_print_manifest()` receives the assigned `device_id` and passes it to `_dispatch_scene_if_enabled()`, which calls `send_to_printer()` directly, bypassing the global `print_dispatch_mode` check. The early-return at `print_queue_service.py:495` (`if mode == "save_form": return None`) is gated by a new `force_dispatch=True` flag so explicit assignments always reach `send_to_printer()`.
- **`__virtual__` bypasses model validation** — routed to `_resolve_virtual_device_id` without model checking; always available in every group dropdown.
- **All-or-nothing for v1** — validation errors produce HTTP 422 with a structured body `{ "groups": [...] }` (top-level, not nested under `"detail"`). Success produces HTTP 200 with all groups `"submitted"`. No mixed response.

---

## Printer Model Selection

`row.printer` (the existing printer group field, e.g. "Form 4BL") continues to drive `plan_build_manifests()` in `build_planning.py:69`. Removing the per-row printer dropdown without a replacement would lock all rows to their current `.printer` value (defaulting to "Form 4BL"), preventing routing cases to a Form 4B device.

**Solution:** Keep the bulk "Change Printer" dropdown (`renderBulkActions`, lines 2041–2073). Its options change from hardcoded `PRINTER_OPTIONS` to **all supported printer models** (`PrinterGroup` values from `schemas.py:10`), **annotated by availability** from `/api/preform-setup/devices`. A model with no connected devices is shown dimmed with a note "(not connected)" — still selectable for planning purposes (e.g. virtual-only debug), but the operator is informed.

This writes to `row.printer` as before, preserving the existing planning path unchanged.

**Summary of UI control changes:**

| Control | Before | After |
|---|---|---|
| Per-row printer dropdown | Editable select (Form 4BL / Form 4B) | Read-only pill (last dispatched printer model) |
| Bulk "Change Printer" | Hardcoded Form 4BL / Form 4B | Supported models annotated by availability |
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

- `planning_status` uses existing `BuildPlanningStatus` enum — `"planned"` or `"non_plannable"` (`schemas.py:11`).
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

- If `printer_assignments` is present: backend re-plans, validates exact `row_ids` match per manifest, validates device model compatibility, then dispatches all-or-nothing with `force_dispatch=True`.
- `"__virtual__"` bypasses model validation and routes to `_resolve_virtual_device_id`.
- If `printer_assignments` is absent: existing behaviour unchanged (backwards compatible).

**Success — HTTP 200:**
```json
{
  "groups": [
    { "manifest_id": "...", "status": "submitted", "row_ids": [1, 2, 3] },
    { "manifest_id": "...", "status": "submitted", "row_ids": [4] }
  ],
  "rows": [/* updated ClassificationRow list */]
}
```

**Failure — HTTP 422** (top-level `groups`, not nested under `"detail"`):
```json
{
  "groups": [
    { "manifest_id": "...", "status": "failed", "error": "Device model mismatch: selected Form 4B, manifest requires Form 4BL", "row_ids": [1, 2, 3] }
  ]
}
```

No jobs are dispatched on 422. The frontend reads `response.groups` directly (not `response.detail.groups`).

---

## Backend Changes

### `process_print_manifest` — `app/services/print_queue_service.py:717`

Gains an optional `device_id: str | None = None` parameter. When provided, it is passed to `_dispatch_scene_if_enabled()` with `force_dispatch=True`.

### `_dispatch_scene_if_enabled` — `app/services/print_queue_service.py:485`

Gains an optional `force_dispatch: bool = False` parameter. When `force_dispatch=True`, the early-return guard at line 495 (`if mode == "save_form": return None`) is skipped and `send_to_printer()` is called directly with the provided `device_id`.

When `device_id` is `"__virtual__"`, route to `_resolve_virtual_device_id` (existing path), skip model validation.

When `device_id` is a real device id:
1. Call `list_devices()`, find device by id, extract `model`.
2. Verify `model` matches manifest `printer_group`. Raise `ValueError` with a clear message if incompatible (caller converts to 422).

The existing fallback (infer from rows, default to "Form 4BL", respect global mode) is kept for calls without `printer_assignments`.

### `row.printer` field

Not reused for physical device identity. Continues as printer group hint for `plan_build_manifests()`. The read-only pill in the work queue table shows the **printer model** (`printer_type`) from the most recent `PrintJob` for that row's case_id — this is the model string (e.g. "Form 4BL"), not a physical device name, which is consistent with what `PrintJob.printer_type` stores. Physical device name is not persisted in v1.

---

## Frontend Changes (`app/static/app.js`)

### Removed
- `PRINTER_OPTIONS` constant (line 20).
- `createPrinterSelect()` function (lines 1063–1097) — per-row printer dropdown.

### Modified
- Bulk "Change Printer" dropdown (`renderBulkActions`, lines 2041–2073) — options change to all supported `PrinterGroup` values annotated by availability from `/api/preform-setup/devices`. Unavailable models shown dimmed with "(not connected)". Writes to `row.printer` as before.
- `sendRowsToPrint(rows)` — opens the Send to Print modal instead of calling the API directly.
- Row rendering — printer cell shows a read-only text pill showing `printer_type` from the last `PrintJob` for that case_id (model string, e.g. "Form 4BL"), or "—".

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
5. **On Send All** — calls `POST /api/uploads/rows/send-to-print` with `printer_assignments`; on 200 closes modal and updates queue; on 422 reads `response.groups` and shows per-group inline errors without closing modal.

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
- Dimmed option style for offline printers and unavailable models.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| PreFormServer offline | "Send to Print" button disabled — existing `canPrint()` gate, no change |
| `available: false` from `/devices` | Modal cannot open (gate should have blocked this; defensive only) |
| No compatible devices for a group | Dropdown shows only "Virtual Printer"; real printer options absent |
| Device model mismatch at dispatch | HTTP 422 `{ "groups": [...] }`; no jobs dispatched; modal stays open with inline errors |
| Stale assignment (row_ids no longer match plan) | HTTP 422; operator re-opens modal to re-plan |
| Non-plannable group in preview | Card shown as disabled with reason; excluded from Send All |
| Model "(not connected)" selected in bulk selector | Allowed for planning; modal will show only Virtual Printer for that group |

---

## Files to Modify

| File | Change |
|---|---|
| `app/routers/preform_setup.py` | Add `GET /api/preform-setup/devices` |
| `app/routers/uploads.py` | Add `GET /api/uploads/rows/preview-batches`; update `send-to-print` request + response schema; return top-level `{ "groups": [...] }` on 422 via `JSONResponse` |
| `app/schemas.py` | Add `DeviceInfo`, `PreviewBatchGroup`, `PrinterAssignment`, `SendToPrintGroupResult`, `SendToPrintResponse` models; update `SendToPrintRequest` |
| `app/services/print_queue_service.py` | Add `device_id` param to `process_print_manifest()`; add `force_dispatch` param to `_dispatch_scene_if_enabled()`; add device model validation |
| `app/services/build_planning.py` | Verify `plan_build_manifests()` is callable standalone for preview-batches endpoint |
| `app/static/index.html` | Add `#send-to-print-modal` markup |
| `app/static/app.js` | Remove `PRINTER_OPTIONS`, `createPrinterSelect`; update bulk model selector with availability annotation; add modal logic |
| `app/static/styles.css` | Add modal + status dot + dimmed styles |

---

## Verification

1. Start app with PreFormServer offline — "Send to Print" button is disabled.
2. Start PreFormServer; click "Send to Print" — modal opens, planned manifest groups shown with unique `manifest_id`s, Virtual Printer present in all dropdowns.
3. Assign Virtual Printer to all groups; click "Send All" — HTTP 200, all groups `"submitted"`, work queue updates.
4. With two physical printers (different models) connected, use bulk model selector to set printer model, then open modal and assign each group to its compatible device — each manifest dispatched to correct device.
5. Attempt to assign a Form 4B device to a Form 4BL manifest — HTTP 422 `{ "groups": [...] }` with per-group error, no jobs dispatched, modal stays open.
6. Change rows between modal open and Send All — HTTP 422 "stale assignment", modal prompts re-open.
7. Two manifests with same compatibility key (overflow) — each has a distinct `manifest_id`; assignments map correctly.
8. Set printer model to Form 4B with no Form 4B device connected — bulk selector shows "(not connected)" annotation; modal shows only Virtual Printer for that group.
9. Call `POST /api/uploads/rows/send-to-print` without `printer_assignments` — existing behaviour unchanged.
