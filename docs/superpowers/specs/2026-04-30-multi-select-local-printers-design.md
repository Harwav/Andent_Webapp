# Multi-Select Local Printer Dispatch

**Date:** 2026-04-30
**Status:** Revised (v5)

---

## Context

Andent Web needs to dispatch selected Ready rows to a specific live local printer without asking the operator to understand build-manifest grouping first. The current draft grouped rows first, then asked for printer assignment per manifest. That is backwards for the desired lab workflow.

The approved workflow is:

1. Select all rows to send.
2. Select the printer to dispatch to.
3. Click Send.
4. Backend groups, validates, quarantines bad cases, dispatches the valid groups, and reports what happened.

The operator chooses the destination printer once. Build grouping remains an implementation detail unless a group cannot be dispatched.

---

## Product Flow

### Work Queue

- Ready rows keep their existing multi-select behavior.
- The bulk actions bar shows a **Printer** selector populated from live `/api/preform-setup/devices`.
- The **Send to Print (n)** button is enabled only when:
  - at least one Ready row is selected,
  - PreFormServer is ready,
  - a printer is selected.
- The row table does not expose per-row printer editing for dispatch. Per-row printer/model fields remain backend planning metadata, not the primary dispatch control.

### Send Action

When the operator clicks Send:

1. Frontend posts selected `row_ids` and one selected `device_id`.
2. Backend refreshes the selected device from PreFormServer.
3. Backend maps that device to its printer model (`Form 4BL`, `Form 4B`, or virtual).
4. Backend plans build manifests using the selected printer model.
5. Backend prevalidates rows and manifests before creating any PreForm scene.
6. Broken STL files quarantine their entire case.
7. Valid remaining cases continue through grouping, layout, validation, save, and dispatch.
8. Response reports submitted groups, quarantined cases, and any blocked groups.

---

## API Design

### `GET /api/preform-setup/devices`

Returns live local devices in a normalized shape:

```json
{
  "available": true,
  "message": null,
  "devices": [
    { "id": "abc-123", "name": "Lab Printer 1", "model": "Form 4BL", "status": "ready", "is_virtual": false }
  ]
}
```

`available: false` means PreFormServer cannot currently provide printer discovery.

### `POST /api/uploads/rows/send-to-print`

Request:

```json
{
  "row_ids": [1, 2, 3, 4],
  "device_id": "abc-123"
}
```

The endpoint no longer requires `printer_assignments` from the frontend for the main workflow. The selected `device_id` is the operator's dispatch decision.

Response:

```json
{
  "groups": [
    { "status": "submitted", "row_ids": [1, 2], "job_name": "260430_CASE-01_CASE-02", "print_job_id": "print-1" }
  ],
  "quarantined_cases": [
    { "case_id": "CASE-03", "row_ids": [3, 4], "reason": "Corrupted STL file: lower.stl - ..." }
  ],
  "blocked_groups": [],
  "rows": []
}
```

HTTP status:

- `200` when at least one group was submitted or all selected rows were handled by quarantine/review states.
- `422` when nothing can be dispatched because the selected printer is invalid, PreFormServer cannot discover devices, all rows are non-plannable, or all selected cases are quarantined.
- `502` when PreFormServer becomes unavailable during scene work after prevalidation.

---

## Backend Dispatch Contract

### Printer Selection

The backend validates the selected `device_id` against a fresh `list_devices()` call. It rejects unknown devices before scene creation. A physical device must expose a supported model. A virtual printer is allowed only when PreFormServer reports a clearly virtual device.

The selected physical printer model drives planning. For example, selecting a `Form 4B` device causes selected rows to be planned as `Form 4B` jobs when their presets support that printer. Rows or cases that cannot be planned for that printer move to Needs Review instead of being silently sent to a different printer.

### Prevalidation

Before any call to `create_scene()` or `import_model()`, the backend validates:

- selected rows exist and are Ready,
- selected device still exists,
- selected device model is supported,
- every STL path exists and is readable,
- every STL passes local `validate_stl_file`,
- presets are compatible with the selected printer model,
- build manifests are plannable.

Local STL validation is intentionally repeated at dispatch time even though upload classification already validates files. Dispatch is a second trust boundary: files can be missing, changed, truncated, or exposed to stricter mesh parsing later.

### Case Quarantine

If any STL in a case fails dispatch prevalidation, the entire case is quarantined:

- every selected row for that `case_id` moves to Needs Review,
- `review_required = true`,
- `review_reason` includes the failing STL and validation message,
- an upload row event records `case_quarantined_before_preform`,
- the case is removed from the dispatch candidate set,
- the remaining selected cases continue.

Quarantine is case-level because a dental case is a unit of clinical work. Dispatching a partial case would create an incomplete print and hide the actual problem.

### Import Failure Resilience

Prevalidation reduces bad imports but cannot prove PreFormServer will accept every mesh. If `import_model()` fails or disconnects PreFormServer:

- do not retry that same STL import in the same run,
- mark the owning case Needs Review with the import error,
- close the current client session,
- probe PreFormServer readiness,
- if managed PreFormServer is down, attempt the existing managed restart path once,
- continue with remaining groups only after readiness is restored,
- otherwise return a structured `502` with the case-level failure details.

Retries remain appropriate for transient connection failures before a model is identified as the trigger. They are not appropriate for repeatedly sending the same suspected bad STL to a fragile external process.

---

## Why Broken STL Files Can Still Crash PreFormServer

PreFormServer should be robust, but Andent Web cannot assume that every malformed or edge-case mesh will be repaired safely by a third-party local process. STL "repair" usually means fixing printable geometry issues after a file is parseable: normals, holes, non-manifold edges, or layout/validation concerns. It does not guarantee safe handling of every corrupted binary, malformed triangle count, huge payload, parser edge case, or preset/material mismatch.

So the app treats PreFormServer as the final print authority, not as the first line of defense. Andent validates cheaply first, quarantines known-bad cases, then asks PreFormServer to layout and validate only candidates that pass local gates.

---

## Performance Budget

Expected additional backend time for prevalidation is small compared with PreForm scene work:

- file stat/readability checks: milliseconds per row,
- STL header/format checks: milliseconds per row,
- mesh parse through `validate_stl_file`: usually tens to hundreds of milliseconds per STL depending on file size,
- manifest planning: milliseconds to low tens of milliseconds for normal batches,
- device discovery: existing PreFormServer HTTP call, usually under the current 5 second timeout.

Target budget:

- typical batch of 10-30 STL files: under 1-3 seconds added before scene creation,
- large files or cold filesystem cache: can be several seconds,
- worst case is bounded by file count, file size, and the existing device discovery timeout.

This is still much cheaper than creating scenes, importing models, auto-layout, saving `.form` files, and recovering from a crashed PreFormServer.

Implementation should measure and log prevalidation duration as `prevalidation_ms` so this can be verified against real lab files.

---

## Frontend Changes

### Removed From Main Flow

- Manifest assignment modal as the primary dispatch flow.
- Per-manifest printer assignment payload.
- Any operator requirement to assign printers after grouping.

### Added

- Bulk printer selector populated from live local devices.
- Printer options show name, model, and status.
- Send button posts `{ row_ids, device_id }`.
- Result handling shows:
  - submitted group count,
  - quarantined case count,
  - blocked/error details when nothing could dispatch.

The UI may still expose a read-only post-send receipt or detail panel showing how selected rows were grouped, but grouping is not a prerequisite for choosing the printer.

---

## Files to Modify

| File | Change |
|---|---|
| `app/routers/preform_setup.py` | Add/keep normalized `GET /api/preform-setup/devices` |
| `app/routers/uploads.py` | Change send-to-print request to accept one `device_id`; return grouped/quarantine result |
| `app/schemas.py` | Add/update device, request, response, group result, and quarantine models |
| `app/services/print_queue_service.py` | Validate selected device, prevalidate STL files, quarantine bad cases, plan for selected printer, dispatch valid groups |
| `app/services/planning_preview.py` | Keep only if needed for receipt/read-only grouping; not required for primary dispatch selection |
| `app/static/app.js` | Replace manifest assignment modal flow with selected-printer dispatch flow |
| `app/static/index.html` | Add any printer selector/result UI hooks needed |
| `app/static/styles.css` | Style printer selector/result/quarantine summaries |
| `tests/test_preform_handoff.py` | Add backend tests for selected-device flow, quarantine, and import-failure resilience |
| `tests/test_frontend_static.py` | Add static tests for selected-printer payload and removal of manifest assignment as primary flow |

---

## Verification

1. Select Ready rows, choose one live `Form 4BL` device, click Send. Backend groups rows and dispatches groups to that device.
2. Select a `Form 4B` device. Compatible cases plan for `Form 4B`; incompatible cases move to Needs Review.
3. Include one corrupted STL in a multi-row case. Entire case is quarantined; other selected cases still dispatch.
4. Make `import_model()` fail for one STL after local prevalidation. That case is marked Needs Review, the same STL is not retried, and remaining work continues only if PreFormServer readiness is restored.
5. Select an unknown/stale `device_id`. Endpoint returns `422` before scene creation.
6. Select virtual printer only when a virtual device is discovered.
7. Measure `prevalidation_ms` in tests or logs and confirm typical prevalidation is small relative to scene creation/import/layout time.
8. Attempt live PreFormServer verification. If a live server cannot be reached, report that missing proof as a blocker rather than claiming full completion.

---

## Out Of Scope

- Automatic STL repair inside Andent Web.
- Trusting PreFormServer to repair corrupted files before local validation.
- Multi-printer split dispatch from one operator Send action.
- Replacing PreFormServer layout, print validation, or queueing.
