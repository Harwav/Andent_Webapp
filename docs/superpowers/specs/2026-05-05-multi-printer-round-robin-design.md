# Multi-Printer Round-Robin Dispatch — Design Spec

**Date:** 2026-05-05
**Status:** Approved

---

## Context

When "Send All" is clicked with multiple printers selected, rows should be distributed across the selected pool in round-robin fashion — grouped by manifest (same material, layer height, print settings). One API call handles all manifests. Round-robin is implicit when 2+ printers are chosen; single-printer selection sends all to that one printer.

---

## Changes

### 1. Frontend — New State

Add to `state` in `app.js`:

```javascript
sendAllPrinterPool: [],      // string[] of selected device_ids
roundRobinIndex: 0,           // current rotation position, persisted in localStorage
```

Existing `autoSendAll.deviceId` remains for single-printer selection.

### 2. Frontend — UI Flow

**Multi-select printer dropdown (triggered by "Send All"):**
- Checkbox-style multi-select list of available printers
- Confirm button submits selection
- If 1 printer selected → single-printer mode (no rotation)
- If 2+ selected → round-robin mode enabled

**Assignment logic (when 2+ printers selected):**
1. Call backend to get manifest plan (grouping by compatibility_key) — or use existing send-to-print that returns manifest info
2. Assign each manifest to `sendAllPrinterPool[roundRobinIndex % pool.length]`
3. Increment `roundRobinIndex` per manifest
4. Store updated `roundRobinIndex` in `localStorage`

### 3. Backend — New Parameter

`POST /uploads/rows/send-to-print` (`SendToPrintRequest` in `uploads.py`):

```python
manifest_device_map: dict[str, str] | None = None  # compatibility_key -> device_id
```

`print_queue_service.py` — `_send_ready_rows_to_device`:
- When `manifest_device_map` is provided, use `manifest_device_map[manifest.compatibility_key]` for dispatch
- When not provided, fall back to existing `device_id` behavior

### 4. Persistence

- `roundRobinIndex` stored in `localStorage`
- When pool changes (printer added/removed), reset `roundRobinIndex` to 0
- `sendAllPrinterPool` also stored in `localStorage` for cross-session recall

### 5. Single vs Multi Printer Behavior

| Selection | Behavior |
|-----------|----------|
| 1 printer | All manifests sent to that printer — `device_id` set, `manifest_device_map` null |
| 2+ printers | Manifests distributed round-robin — `device_id` null, `manifest_device_map` populated |

---

## API Request Shape

```json
{
  "row_ids": [1, 2, 3, ...],
  "device_id": null,
  "manifest_device_map": {
    "Form4BL_TGX-11_0.05mm": "device-uuid-1",
    "Form4BL_TGX-11_0.03mm": "device-uuid-2",
    "Form4B_TGX-14_0.05mm": "device-uuid-1"
  }
}
```

`device_id` is used when single printer selected (no `manifest_device_map`). When `manifest_device_map` is present, `device_id` is ignored.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/static/app.js` | Multi-select printer dropdown, round-robin assignment, localStorage persistence |
| `app/static/index.html` | Multi-select printer picker UI markup |
| `app/routers/uploads.py` | Accept `manifest_device_map` in `SendToPrintRequest` schema |
| `app/services/print_queue_service.py` | `_send_ready_rows_to_device` uses per-manifest device from map |

---

## UX Details

- **Printer pool empty on first use** → user must select at least 1 printer before sending
- **Pool change detected** → reset `roundRobinIndex` to 0 to avoid out-of-bounds assignment
- **All printers in pool busy** → existing build-lane-lock behavior applies (job held)
- **Auto-send (Feature 1) + round-robin** → works together; auto-send reuses the stored `sendAllPrinterPool`