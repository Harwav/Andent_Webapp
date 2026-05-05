# One-click "Send All to Print" — Design Spec

**Date:** 2026-05-05
**Status:** Approved

---

## Context

Currently bulk-send only sends the 50 visible rows in the current page. Operators want a one-click "Send All" that sends ALL ready rows in File Analysis across all pages, plus an auto-send mechanism for rows that become ready during an active session.

The backend `list_queue_rows()` already returns all active rows (no pagination limit). The frontend has all rows in `state.activeRows`. The 50-row limit is purely a display constraint in the rendering layer.

---

## Changes

### 1. Frontend — New State

Add to `state` object in `app.js`:

```javascript
autoSendAll: {
  enabled: false,    // toggled by Send All button
  deviceId: null,    // selected printer device_id
}
```

### 2. Frontend — UI Elements

**Status bar button (index.html):**
- "Send All" pill appears right of status text when PreForm is ready
- Click → if no `deviceId` selected, show printer dropdown; on select → set enabled + send ready rows
- While enabled → accent background, "Auto-send ON" label
- Click again while active → disables auto-send

**Bulk-action bar button:**
- "Send All" button in the bulk-action bar area (top of table)
- Same behavior as status bar button

**Printer dropdown:**
- Inline dropdown listing available printers from `dispatchDeviceOptions()`
- Selected `deviceId` stored in `localStorage` for cross-session persistence

### 3. Frontend — Polling Logic (10s interval)

When `autoSendAll.enabled === true`, each poll additionally:
1. Filter `state.activeRows` for rows where:
   - `queue_section == 'analysis'`
   - `status == 'Ready'`
   - not already in a print job (check `linked_job_id` is null)
2. Call `sendRowsToPrint(rows, state.autoSendAll.deviceId)` for those rows

### 4. Backend — No Changes

Existing `POST /uploads/rows/send-to-print` already handles sending ready rows. The existing filter `status == 'Ready'` is applied server-side.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/static/app.js` | `state.autoSendAll`, Send All button handlers, polling auto-send logic |
| `app/static/index.html` | Status bar + bulk-action bar Send All button markup |
| `app/static/styles.css` | Send All active/enabled styling |

---

## UX Details

- **0 ready rows on click** → show "No rows to send" toast, do NOT enable auto-send
- **Send failure** → show error toast, auto-send stays enabled; next poll retries
- **PreForm not ready** → Send All button disabled (same gate as existing print buttons)
- **Cross-session persistence** → selected `deviceId` saved to `localStorage`
- **Only File Analysis section** → rows in `in_progress` or other sections are never auto-sent