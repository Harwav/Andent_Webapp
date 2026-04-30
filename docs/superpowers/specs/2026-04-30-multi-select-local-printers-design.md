# Multi-Select Local Printers for Send to Print

**Date:** 2026-04-30  
**Status:** Approved

---

## Context

Andent Web currently routes print jobs to one of two hardcoded printer *groups* ("Form 4BL" / "Form 4B"). This works for a single-printer lab but breaks down when a lab has multiple physical Formlabs printers of the same model — there is no way to target a specific machine. The operator also has no visibility into which device will receive a job before dispatching.

The goal is to replace the hardcoded printer group concept with live physical printer selection at the point of dispatch, via a "Send to Print" modal that shows detected devices and lets the operator assign each build group to a specific printer.

---

## Architecture

### Data Flow

1. Operator clicks **Send to Print (n)** in the bulk actions bar (only enabled when PreFormServer is reachable — existing `canPrint()` gate, unchanged).
2. Frontend calls `GET /api/preform-setup/devices` to fetch live printer list from PreFormServer.
3. Frontend calls `GET /api/uploads/rows/preview-batches?row_ids=…` to compute build groups for the selected rows.
4. Modal renders — one card per build group, each with a printer dropdown.
5. Operator assigns a printer to each group; clicks **Send All**.
6. Frontend calls `POST /api/uploads/rows/send-to-print` with `row_ids` + `printer_assignments`.
7. Backend dispatches each group to its assigned device independently.

### Printer Group Concept

The hardcoded `PRINTER_OPTIONS = ["Form 4BL", "Form 4B"]` constant is retired. Physical device selection replaces printer group selection. Printer model (Form 4BL / Form 4B) is inferred from the selected device for compatibility grouping purposes. The per-row printer dropdown (`createPrinterSelect`) and bulk "Change Printer" dropdown are removed from the work queue UI. The `.printer` field on rows becomes a read-only informational pill showing last assigned device.

---

## New API Endpoints

### `GET /api/preform-setup/devices`

Added to `app/routers/preform_setup.py`.

- Calls `preform_client.list_devices()`.
- Returns `{ devices: [{ id, name, model, status }] }`.
- Returns empty list (not an error) if PreFormServer is unreachable — upstream `canPrint()` gate means this state should not be reachable from the modal, but defensive behaviour is appropriate.
- No caching — always live.

### `GET /api/uploads/rows/preview-batches`

Added to `app/routers/uploads.py`.

- Query param: `row_ids` (comma-separated integers).
- Runs `_group_profiles_by_compatibility()` from `app/services/build_planning.py` (read-only, no side effects).
- Returns `{ groups: [{ compatibility_key, printer_model, case_ids, row_ids }] }`.
- `printer_model` in each group is derived from the row's existing `.printer` field if set, otherwise defaults to "Form 4BL". This is used only for display in the modal header — the operator's device selection at Send All time is the authoritative routing.
- Safe to call multiple times (idempotent).

---

## Modified API Endpoints

### `POST /api/uploads/rows/send-to-print`

Request body gains an optional field:

```json
{
  "row_ids": [1, 2, 3, 4],
  "printer_assignments": [
    { "device_id": "abc-123", "row_ids": [1, 2, 3] },
    { "device_id": "__virtual__", "row_ids": [4] }
  ]
}
```

- If `printer_assignments` is present, each sub-list is dispatched to its assigned device independently.
- `"__virtual__"` routes to the existing virtual dispatch path in `_dispatch_scene_if_enabled`.
- If `printer_assignments` is absent, existing behaviour is unchanged (backwards compatible).

---

## Backend Changes

### `_resolve_device_id` — `app/services/print_queue_service.py`

When a `device_id` is explicitly provided via `printer_assignments`, it is used directly — no inference from row `.printer` field. The existing fallback (infer from rows, default to "Form 4BL") is kept for calls without `printer_assignments`.

### Virtual Printer handling

`"__virtual__"` as `device_id` bypasses `_resolve_device_id` and routes directly into the existing `_resolve_virtual_device_id` path. No new dispatch mode logic needed.

---

## Frontend Changes (`app/static/app.js`)

### Removed
- `PRINTER_OPTIONS` constant (line 20).
- `createPrinterSelect()` function (lines 1063–1097) — per-row printer dropdown.
- Bulk "Change Printer" dropdown in `renderBulkActions()` (lines 2041–2073).

### Modified
- `sendRowsToPrint(rows)` — instead of calling the API directly, opens the Send to Print modal.
- Row rendering — printer cell shows a read-only text pill with last-assigned device name (or "—").

### Added: Send to Print Modal

Triggered by the existing "Send to Print" button. Lifecycle:

1. **Open** — fetch `/api/preform-setup/devices` and `/api/uploads/rows/preview-batches` in parallel.
2. **Render** — one card per build group:
   - Header: `{printer_model} · {material} · {layer_height}`
   - Sub-line: case IDs
   - Dropdown: live device list + always-present "Virtual Printer" option at the bottom, separated by a divider
3. **Printer dropdown options:**
   - Real printers: `● {name}  ({model}, {status})` — status shown as colored dot (green = ready, amber = busy, red = offline); offline printers shown dimmed but selectable
   - Separator `─────`
   - `◌ Virtual Printer  (simulate)`
4. **Send All button** — disabled until every group has a printer assigned.
5. **On Send All** — calls `POST /api/uploads/rows/send-to-print` with full `printer_assignments`; closes modal on success; shows existing success/error status handling.

### Modal HTML (`app/static/index.html`)

Add modal markup (hidden by default):

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
| PreFormServer offline | "Send to Print" button disabled (existing `canPrint()` gate — no change) |
| Device disappears between modal open and Send All | Backend returns 502 for that group; frontend shows inline per-group error; other groups dispatched successfully |
| No printers returned by `/devices` | Modal dropdown shows only "Virtual Printer" |
| All groups have one obvious printer | Modal pre-selects it; operator just confirms |

---

## Files to Modify

| File | Change |
|---|---|
| `app/routers/preform_setup.py` | Add `GET /api/preform-setup/devices` |
| `app/routers/uploads.py` | Add `GET /api/uploads/rows/preview-batches`; update `send-to-print` schema |
| `app/schemas.py` | Add `DeviceInfo`, `PreviewBatchGroup`, `PrinterAssignment` models; update `SendToPrintRequest` |
| `app/services/print_queue_service.py` | Update `send_ready_rows_to_print` + `_resolve_device_id` to accept explicit device_id |
| `app/services/build_planning.py` | Expose `_group_profiles_by_compatibility` for preview-batches endpoint |
| `app/static/index.html` | Add `#send-to-print-modal` markup |
| `app/static/app.js` | Remove `PRINTER_OPTIONS`, `createPrinterSelect`, bulk printer dropdown; add modal logic |
| `app/static/styles.css` | Add modal + status dot styles |

---

## Verification

1. Start the app; confirm "Send to Print" button is disabled when PreFormServer is not running.
2. Start PreFormServer with at least one virtual printer registered; click "Send to Print" — modal opens, virtual printer appears in dropdown.
3. Assign virtual printer to all groups; click "Send All" — jobs dispatch, work queue updates.
4. With two physical printers connected, assign different printers to two groups — each job goes to its assigned device.
5. With an offline printer selected at Send All time — that group shows an inline error, other groups succeed.
6. Call `POST /api/uploads/rows/send-to-print` without `printer_assignments` — existing behaviour unchanged.
