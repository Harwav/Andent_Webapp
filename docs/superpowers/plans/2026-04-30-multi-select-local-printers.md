# Multi-Select Local Printers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators preview build manifests, assign each manifest to a discovered physical or virtual PreForm device, and submit all assignments only after server-side validation succeeds.

**Architecture:** Add assignment DTOs and manifest preview helpers, then extend send-to-print with a validated assignment path that prevalidates every manifest before any PreForm scene work begins. Preserve legacy send-to-print behavior when assignments are omitted.

**Tech Stack:** FastAPI, Pydantic, SQLite, vanilla JavaScript, pytest.

---

### Task 1: Backend Contracts and Preview

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/services/planning_preview.py`
- Modify: `app/routers/uploads.py`
- Modify: `app/routers/preform_setup.py`
- Test: `tests/test_preform_handoff.py`

- [ ] Add tests for POST `/api/uploads/rows/preview-batches` returning manifest groups with stable assignment IDs.
- [ ] Add tests for GET `/api/preform-setup/devices` returning normalized device records and availability.
- [ ] Implement schemas and route/service code to pass those tests.

### Task 2: Assignment Validation and Dispatch

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/services/print_queue_service.py`
- Modify: `app/routers/uploads.py`
- Test: `tests/test_preform_handoff.py`

- [ ] Add tests proving stale row assignments, model mismatch, unknown devices, and missing virtual devices return HTTP 422 with top-level `groups` and do not create scenes.
- [ ] Add tests proving valid assignments submit to the selected real or virtual devices.
- [ ] Implement endpoint-level all-assignment validation before calling `process_print_manifest()`.
- [ ] Add explicit `device_id` dispatch parameters while preserving legacy behavior without assignments.

### Task 3: Persist Device Metadata

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/database.py`
- Modify: `app/services/print_queue_service.py`
- Test: `tests/test_preform_handoff.py`

- [ ] Add tests proving selected physical `printer_device_id` and `printer_device_name` are stored on `PrintJob`.
- [ ] Add SQLite columns, schema fields, insert/update/load wiring, and result propagation.

### Task 4: Frontend Modal

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] Add static tests for the modal hooks, POST preview call, assignment payload, and 422 group error handling.
- [ ] Replace direct send-to-print with modal preview/assignment flow.
- [ ] Keep bulk model changes backed by `row.printer`; remove per-row mutable printer selectors.

### Task 5: Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-04-30-multi-select-local-printers-design.md`

- [ ] Update the spec with the approved review changes.
- [ ] Run focused pytest files.
- [ ] Run the full pytest suite if time permits.
- [ ] Attempt live PreFormServer verification; report a blocker if no live server is reachable.
