# History Tab Redesign — Design Spec

**Date:** 2026-05-05
**Status:** Approved

---

## Context

The History tab currently uses a simpler `processed-table` (8 columns) that lacks the visual richness and data density of the Work Queue's active table. It should be updated to match the Work Queue's column style while remaining read-only (no editing, no bulk actions).

---

## Changes

### 1. Preview Thumbnails Column

Add a `.col-preview` column (same as Work Queue's active table):
- Shows 64x64px STL snapshot via `renderStlSnapshotPng()`
- Same placeholder/text treatment as Work Queue when snapshot unavailable
- Implemented using existing thumbnail system in `state.thumbnailSnapshots`

### 2. Model Type and Preset Columns

Add display-only columns (no dropdown/edit):
- **Model Type** — shows `row.model_type` as a label chip
- **Preset** — shows `row.preset` as a label chip
- No edit controls, just display
- Same styling as the Work Queue's read-only display (`.model-type` / `.preset` labels)

### 3. Dimensions Column

Add `.col-dimensions` showing `x × y × z mm`:
- Format: `row.dimension_x_mm × row.dimension_y_mm × row.dimension_z_mm`
- If any dimension is missing, show `-`
- Same format as Work Queue dimensions column

### 4. Printer Pill (already exists — verify consistency)

Check existing `printerLabelForRow(row)` in app.js:
- Shows `linkedJob?.printer_type || row.printer || "-"`
- Ensure consistent with Work Queue printer pill styling

### 5. HTML Structure — `processed-table`

Update `processed-table` to match `active-table` column structure:

```html
<table class="data-table processed-table">
  <thead>
    <tr>
      <th class="col-preview">Preview</th>
      <th class="col-file">File</th>
      <th class="col-case">Case ID</th>
      <th class="col-model">Model Type</th>
      <th class="col-preset">Preset</th>
      <th class="col-dimensions">Dimensions</th>
      <th class="col-meta">Printer</th>
      <th class="col-status">Status</th>
      <th class="col-date">Date</th>
    </tr>
  </thead>
  <tbody id="history-body"></tbody>
</table>
```

Note: No `.col-select` column (no bulk actions in History).

### 6. app.js — `renderHistoryRows()`

Update to render:
- Thumbnail via `getThumbnailSnapshotKey(row)` and `createThumbnail(row)`
- Model type label (from `row.model_type`)
- Preset label (from `row.preset`)
- Dimensions string
- Printer pill (existing)

All other existing History behavior preserved (job link, date, status chip).

---

## Files to Modify

| File | Change |
|------|--------|
| `app/static/index.html` | Update `processed-table` columns to match Work Queue structure |
| `app/static/app.js` | Update `renderHistoryRows()` to render new columns |
| `app/static/styles.css` | Ensure dimensions label styling, preview thumbnail sizing |

---

## UX Details

- **Missing dimensions** → show `-` in dimensions column
- **Missing model_type or preset** → show `-` as label
- **No thumbnail available** → same placeholder as Work Queue ("STL" or "Rendering")
- **No interactive controls** — History is read-only, no edit dropdowns, no checkboxes, no remove button