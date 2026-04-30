# Multi-Select Local Printers for Send to Print

**Date:** 2026-04-30  
**Status:** Revised (v2)

---

## Context

Andent Web currently routes print jobs to one of two hardcoded printer *groups* ("Form 4BL" / "Form 4B"). This works for a single-printer lab but breaks down when a lab has multiple physical Formlabs printers of the same model — there is no way to target a specific machine. The operator also has no visibility into which device will receive a job before dispatching.

The goal is to replace the hardcoded printer group concept with live physical printer selection at the point of dispatch, via a "Send to Print" modal that shows detected devices and lets the operator assign each planned build manifest to a specific printer.

---

## Architecture

### Data Flow

1. Operator clicks **Send to Print (n)** in the bulk actions bar (only enabled when PreFormServer is reachable — existing `canPrint()` gate, unchanged).
2. Frontend calls `GET /api/preform-setup/devices` and `GET /api/uploads/rows/preview-batches?row_ids=…` in parallel.
3. Modal renders — one card per planned **BuildManifest**, each showing compatible devices in a dropdown.
4. Operator assigns a printer to each manifest group; clicks **Send All**.
5. Frontend calls `POST /api/uploads/rows/send-to-print` with `printer_assignments` keyed by `group_id`.
6. Backend re-plans from `row_ids`, validates each assignment matches the current manifest and that the selected device model is compatible, then dispatches each manifest to its assigned device.

### Key Design Decisions

- **BuildManifest is the stable unit of assignment** — the modal shows actual planned manifests (from `plan_build_manifests()`), not raw compatibility buckets. This ensures what the operator sees matches exactly what gets dispatched.
- **Device compatibility is server-enforced** — the backend calls `list_devices()`, resolves the selected device's model, and verifies it matches the manifest's `printer_group`. Incompatible assignments return 409/422.
- **Explicit assignments bypass the global dispatch mode** — when `printer_assignments` is present, each manifest is dispatched directly to its selected device regardless of `ANDENT_WEB_PRINT_DISPATCH_MODE`. Legacy calls without `printer_assignments` preserve existing mode behaviour.
- **Partial success is all-or-nothing for v1** — simpler and safer; avoids transaction boundary complexity. A structured per-group response is defined for future partial-success support.

### Printer Group Concept

The hardcoded `PRINTER_OPTIONS = ["Form 4BL", "Form 4B"]` constant is retired. Physical device selection replaces printer group selection. Printer model (Form 4BL / Form 4B) continues to drive build planning — it is now inferred from the selected device at dispatch time and validated server-side. The per-row printer dropdown (`createPrinterSelect`) and bulk "Change Printer" dropdown are removed from the work queue UI.

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
- Calls `plan_build_manifests(selected_rows)` from `app/services/build_planning.py` — the same planner used at dispatch time, not `_group_profiles_by_compatibility()`.
- Read-only — no side effects, safe to call multiple times.

Response:
```json
{
  "groups": [
    {
      "group_id": "form-4bl|precision-model-v1|100",
      "row_ids": [1, 2, 3],
      "case_ids": ["Case-01", "Case-02", "Case-03"],
      "compatibility_key": "form-4bl|precision-model-v1|100",
      "printer_model": "Form 4BL",
      "material_label": "Precision Model V1",
      "layer_height_microns": 100,
      "planning_status": "plannable",
      "non_plannable_reason": null
    }
  ]
}
```

- `planning_status`: `"plannable"` or `"non_plannable"`. Non-plannable groups are shown in the modal as disabled cards with `non_plannable_reason` displayed.

---

## Modified API Endpoints

### `POST /api/uploads/rows/send-to-print`

Request body gains an optional `printer_assignments` field:

```json
{
  "row_ids": [1, 2, 3, 4],
  "printer_assignments": [
    { "group_id": "form-4bl|precision-model-v1|100", "device_id": "abc-123", "row_ids": [1, 2, 3] },
    { "group_id": "form-4b|lt-clear-v2|100",         "device_id": "__virtual__", "row_ids": [4] }
  ]
}
```

- If `printer_assignments` is present: backend re-plans from `row_ids`, verifies each assignment's `group_id` matches a current manifest, validates device model compatibility, then dispatches. All-or-nothing for v1.
- `"__virtual__"` routes to the existing `_resolve_virtual_device_id` path.
- If `printer_assignments` is absent: existing behaviour unchanged (backwards compatible).

Response (v1 — all-or-nothing):
```json
{
  "groups": [
    { "group_id": "...", "status": "submitted", "row_ids": [...] },
    { "group_id": "...", "status": "failed",    "error": "Device model mismatch", "row_ids": [...] }
  ],
  "rows": [/* updated ClassificationRow list */]
}
```

Even in v1 (all-or-nothing), the response shape uses this structured format so the frontend can render per-group inline errors if the whole operation fails validation before dispatch begins.

---

## Backend Changes

### `_resolve_device_id` — `app/services/print_queue_service.py`

When `device_id` is explicitly provided:
1. If `device_id == "__virtual__"` → route to `_resolve_virtual_device_id`, existing path.
2. Otherwise: call `list_devices()`, find device by id, extract `model`, verify it matches manifest `printer_group`. Return 409/422 with per-group error if incompatible.

The existing fallback (infer from rows, default to "Form 4BL") is kept for calls without `printer_assignments`.

### Dispatch mode

Explicit `printer_assignments` bypass `ANDENT_WEB_PRINT_DISPATCH_MODE` — each manifest is dispatched directly to its assigned device (calls `send_to_printer()`). Legacy calls without `printer_assignments` continue to respect the global mode.

### `row.printer` field

The `.printer` column on `ClassificationRow` is **not** reused for physical device identity. It remains as a legacy printer group hint (used only by the old fallback path). The read-only pill shown in the table is display-only and is populated from the last dispatched job's `printer_type`, not from `row.printer`. No new `last_printer_device_id` fields are added in v1 — the pill simply shows the `printer_type` from the most recent `PrintJob` for that row's case_id, if available.

---

## Frontend Changes (`app/static/app.js`)

### Removed
- `PRINTER_OPTIONS` constant (line 20).
- `createPrinterSelect()` function (lines 1063–1097) — per-row printer dropdown.
- Bulk "Change Printer" dropdown in `renderBulkActions()` (lines 2041–2073).

### Modified
- `sendRowsToPrint(rows)` — opens the Send to Print modal instead of calling the API directly.
- Row rendering — printer cell shows a read-only text pill (last dispatched device name from PrintJob, or "—").

### Added: Send to Print Modal

Triggered by the existing "Send to Print" button. Lifecycle:

1. **Open** — fetch `/api/preform-setup/devices` and `/api/uploads/rows/preview-batches` in parallel.
2. **Render** — one card per planned manifest group:
   - Header: `{printer_model} · {material} · {layer_height}`
   - Sub-line: case IDs
   - Dropdown: devices filtered to compatible model + always-present "Virtual Printer" at the bottom, separated by a divider
   - Non-plannable groups shown as disabled cards with reason text
3. **Printer dropdown options (per group):**
   - Real printers matching `printer_model`: `● {name}  ({model}, {status})` — status dot (green = ready, amber = busy, red = offline); offline printers dimmed but selectable
   - Separator `─────`
   - `◌ Virtual Printer  (simulate)`
4. **Send All button** — disabled until every plannable group has a printer assigned.
5. **On Send All** — calls `POST /api/uploads/rows/send-to-print` with `printer_assignments`; on success closes modal and updates queue; on failure shows per-group inline errors from the structured response.

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
- Dimmed option style for offline/incompatible printers.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| PreFormServer offline | "Send to Print" button disabled — existing `canPrint()` gate, no change |
| `available: false` from `/devices` | Modal cannot open (gate should have blocked this; defensive only) |
| No compatible devices for a group | Dropdown shows only "Virtual Printer"; real printer options absent |
| Device model mismatch at dispatch | Backend returns 409/422; structured response shows per-group error; no jobs dispatched (v1 all-or-nothing) |
| Assignment group_id no longer matches manifest | Backend returns 422 "stale assignment"; operator re-opens modal to re-plan |
| Non-plannable group in preview | Card shown as disabled with reason; excluded from Send All |

---

## Files to Modify

| File | Change |
|---|---|
| `app/routers/preform_setup.py` | Add `GET /api/preform-setup/devices` |
| `app/routers/uploads.py` | Add `GET /api/uploads/rows/preview-batches`; update `send-to-print` request + response schema |
| `app/schemas.py` | Add `DeviceInfo`, `PreviewBatchGroup`, `PrinterAssignment`, `SendToPrintGroup` models; update `SendToPrintRequest` and response |
| `app/services/print_queue_service.py` | Update `send_ready_rows_to_print` + `_resolve_device_id` to accept explicit `device_id`; add device model validation |
| `app/services/build_planning.py` | Expose `plan_build_manifests()` for use by preview-batches endpoint (may already be callable; verify) |
| `app/static/index.html` | Add `#send-to-print-modal` markup |
| `app/static/app.js` | Remove `PRINTER_OPTIONS`, `createPrinterSelect`, bulk printer dropdown; add modal logic |
| `app/static/styles.css` | Add modal + status dot styles |

---

## Verification

1. Start app with PreFormServer offline — "Send to Print" button is disabled.
2. Start PreFormServer; click "Send to Print" — modal opens, planned manifest groups shown, Virtual Printer present in all dropdowns.
3. Assign Virtual Printer to all groups; click "Send All" — jobs dispatch, work queue updates.
4. With two physical printers (different models) connected, assign each group to a compatible device — each manifest dispatched to correct device.
5. Attempt to assign a Form 4B device to a Form 4BL manifest — backend returns 422 with clear per-group error; no jobs dispatched.
6. Call `POST /api/uploads/rows/send-to-print` without `printer_assignments` — existing behaviour unchanged.
7. Rows between preview-batches call and Send All change status — backend returns 422 "stale assignment"; modal prompts re-open.
