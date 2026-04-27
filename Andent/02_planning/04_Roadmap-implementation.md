# Andent Web: Implementation Roadmap

> **Created:** 2026-04-18
> **Status:** Active
> **Current Phase:** Repository implementation is complete for the current scope, including preset/printer/holding policy; live acceptance validation is next

---

## Overview

This roadmap defines the phased implementation for Andent Web Auto Prep. The scope has been simplified based on architecture clarification: **PreFormServer handles orient/pack, supports, dispatch, and tracking**. Andent Web focuses on intake, classification, and handoff.

Historical effort and file-estimate tables are retained as planning reference. Status sections in this document are the authoritative view of current repository maturity.

---

## Progress Summary

| Phase | Name | Status | Repository State | Verification State |
|-------|------|--------|------------------|--------------------|
| Phase 0 | Classification Intake | COMPLETE | Delivered | Mostly covered |
| Phase 1 | PreFormServer Handoff + Print Queue | COMPLETE (repo) | Major surfaces plus printer-aware Form 4B/Form 4BL build manifests, printer edits, and held-build release implemented | Automated verification green; live validation pending |
| Phase 2 | Enhanced Queue Features | PARTIALLY IMPLEMENTED | Several UX features already landed | Uneven coverage |
| Phase 3 | Validation & Metrics | PARTIALLY IMPLEMENTED | Metrics/API scaffolding exists | Not wired to live workflow proof |
| Phase 4 | Production Hardening | PARTIALLY IMPLEMENTED | Health/network basics exist | Production hardening incomplete |

**Overall Status:** The repository is well beyond Phase 0, the automated test suite is currently green, and the remaining gaps are mainly launch-proof and operational validation.

### PRD Acceptance Status (Compact)

| PRD Acceptance Criterion | Status |
|--------------------------|--------|
| Straight-through processing `>=95%` at launch | Partial |
| Standard cases complete model type detection without touch | Done |
| Standard cases complete preset assignment without touch | Done |
| Standard cases complete case ID confirmation without touch | Partial |
| Human review limited to low-confidence model type matches | Done |
| Human review limited to ambiguous or missing case IDs | Done |
| Human-reviewed outliers remain `<=2%` | Partial |
| Standard die/tooth cases are not blocked by the old MVP safety gate | Done |
| Compatible mixed presets share Form 4B/Form 4BL builds without splitting cases | Done |
| Planner uses printer-aware XY budgets and startup-case seeding | Done |
| Operators can choose printer group per row or in bulk | Done |
| Below-target final builds hold until target, cutoff, or operator release | Done |
| Andent Web sends prepared jobs to PreFormServer | Done |

Source of truth: see the line-by-line checklist in `Andent/02_planning/01_PRD-andent-web.md`.

---

## Phase 0: Classification Intake ✅ COMPLETE

### Achieved Features

| Feature | Status | Location |
|---------|--------|----------|
| FastAPI server | ✅ | `andent_web/app/main.py` |
| STL upload endpoint | ✅ | `routers/uploads.py` |
| Classification logic | ✅ | `services/classification.py` |
| SQLite persistence | ✅ | `database.py` |
| Schema definitions | ✅ | `schemas.py` |
| Browser UI (Active/Processed tabs) | ✅ | `static/index.html`, `app.js` |
| Model Type detection (5 types) | ✅ | Ortho-Solid/Hollow, Die, Tooth, Splint |
| Case ID extraction | ✅ | From filename |
| Confidence levels | ✅ | high/medium/low → Ready/Check/Needs Review |
| Thumbnail generation (SVG) | ✅ | `generate_thumbnail_svg()` |
| Duplicate detection (content hash) | ✅ | `file_content_hash()` |
| Row editing (Model Type/Preset) | ✅ | PATCH `/api/uploads/rows/{id}` |
| Queue pagination (50 per page) | ✅ | `list_queue_rows()` |
| Send-to-print endpoint surface | ✅ | POST `/api/uploads/rows/send-to-print` (now backed by Phase 1 handoff code) |
| Allow duplicate action | ✅ | POST `/api/uploads/rows/allow-duplicate` |
| Row removal | ✅ | DELETE `/api/uploads/rows/{id}` |
| Classification parallelization | Implemented | `classify_uploaded_files_parallel()` exists; launch metrics remain unproven |

### Exit Criteria Met

- ✅ Server starts and accepts STL uploads
- ✅ Returns classification table per file
- ✅ Browser page renders rows with Active/Processed tabs
- ✅ Model Type and Preset are editable
- ✅ Dimensions and confidence visible
- ✅ Ambiguous/missing case IDs flagged (review_required, review_reason)
- ✅ Thumbnails render correctly
- ✅ Duplicate detection works

---

## Phase 1: PreFormServer Handoff + Print Queue Tab ✅ REPOSITORY COMPLETE

### Goal

Complete PreFormServer integration with automated batching, real handoff, and new Print Queue tab for job monitoring.

### Current Status (2026-04-27)

This phase is no longer just planned work. The repository already contains:

- batching logic and job naming
- `PreFormClient` and `FormlabsWebClient`
- preset catalog and compatibility-aware Form 4B/Form 4BL build manifests
- printer-aware XY budgets for `Form 4B` and `Form 4BL`
- bounded case-ordering strategy: startup seeding, descending pass, then smallest fillers
- durable row and bulk printer-group edits
- density-based build holding, persisted hold metadata, and Release now
- `print_jobs` schema and CRUD helpers
- real handoff routing from `/api/uploads/rows/send-to-print`
- Print Queue API/UI, status sync, and screenshot caching

What still blocks full launch sign-off is external validation quality:

- live PreFormServer/Formlabs service validation has not been run in this repository session
- target operational metrics still need evidence from real workflow runs

### Phase 1 Scope (Finalized)

| Feature | Description | Effort | Priority | Dependencies |
|---------|-------------|--------|----------|--------------|
| **Build Planning Logic** | Group Ready rows into whole-case Form 4B/Form 4BL manifests by compatible printer group/material/layer-height, auto-generate job names, and apply printer-aware case seeding | 1 day | P0 | None |
| **Preset Configuration Update** | Ortho/Hollow/Die lay flat; Tooth auto-supports; All use Precision Model Resin 100µm | 0.5 day | P0 | Batching |
| **Real Handoff Endpoint** | Replace simulated send-to-print with PreFormServer API calls | 1 day | P0 | Preset config |
| **FormlabsWebClient** | New client for Formlabs Web API authentication and queries | 1 day | P0 | None |
| **Print Queue Database Schema** | Add print_jobs table, link to upload rows | 0.5 day | P0 | Schema design |
| **Print Queue Tab UI** | New tab with job cards, screenshots, status badges | 1.5 days | P0 | Database |
| **Status Polling Service** | Backend polls Formlabs API every 5s, frontend polls backend | 1 day | P0 | WebClient |
| **Screenshot Display** | Fetch and display job screenshots (click to zoom) | 0.5 day | P1 | Status polling |
| **Connection Error Handling** | Handle PreFormServer/Formlabs API failures gracefully | 0.5 day | P1 | Handoff + WebClient |
| **Durable Overrides** | Persist Model Type/Preset edits across sessions | 0.5 day | P2 | Database |

**Total Estimated: 8 days**

### Phase 1 Files to Modify/Create

| File | Purpose | Lines Est. |
|------|---------|------------|
| `app/services/preform_client.py` | PreFormServer local API client | ~200 |
| `app/services/formlabs_web_client.py` | Formlabs Web API client (new) | ~150 |
| `app/services/print_queue_service.py` | Batching + job management (new) | ~300 |
| `app/routers/uploads.py` | Real handoff endpoint | +100 |
| `app/routers/print_queue.py` | Print queue API endpoints (new) | ~200 |
| `app/database.py` | Add print_jobs table schema | +80 |
| `app/schemas.py` | Print job schemas | +50 |
| `app/config.py` | Add Formlabs API env vars | +20 |
| `app/static/index.html` | Print Queue tab UI | +100 |
| `app/static/app.js` | Print Queue frontend logic | +400 |
| `app/static/styles.css` | Print Queue styling | +200 |

### Phase 1 Test Plan

| Test | Description | Priority |
|------|-------------|----------|
| `test_build_planning` | Cases stay intact, compatible presets mix, incompatible presets do not mix | P0 |
| `test_batching_logic` | Compatibility-aware grouping remains deterministic | P0 |
| `test_job_name_generation` | YYMMDD-001 format works | P0 |
| `test_preform_client_create_scene` | Scene creation via PreFormServer | P0 |
| `test_preform_client_import_model` | STL import to scene | P0 |
| `test_preform_client_send_to_printer` | Handoff to printer group | P0 |
| `test_formlabs_web_client_auth` | API token authentication | P0 |
| `test_formlabs_web_client_list_jobs` | Fetch print jobs from API | P0 |
| `test_print_queue_persistence` | Jobs saved to database | P0 |
| `test_status_polling` | Backend polls Formlabs API | P0 |
| `test_screenshot_fetch` | Screenshot retrieval and display | P1 |
| `test_connection_error_handling` | Graceful failure on API errors | P1 |
| `test_durable_override` | Override persistence across sessions | P2 |

### Phase 1 Exit Criteria

| Criterion | Current Status | Notes |
|-----------|----------------|-------|
| Build planning groups Ready cases by Form 4B/Form 4BL compatibility while preserving case cohesion | Implemented and tested | `tests/test_build_planning.py`, `tests/test_batching.py` |
| Planner uses printer-aware XY budgets so `Form 4B` and `Form 4BL` do not share the same effective heuristic capacity | Implemented and tested | `tests/test_preset_catalog.py`, `tests/test_build_planning.py` |
| Planner seeds new builds with printer-aware startup windows (`Form 4B -> 3`, `Form 4BL -> 8`) and then switches from descending to smallest fillers on first fit miss | Implemented and tested | `tests/test_build_planning.py` |
| Printer group edits persist for rows and bulk selections | Implemented and tested | `tests/test_durable_overrides.py`, `tests/test_frontend_static.py`, `tests/release_gate/bulk-actions.spec.ts` |
| Final below-target builds can hold and release by density target, cutoff, or operator action | Implemented and tested | `tests/test_print_queue.py`, `tests/test_preform_handoff.py`, `tests/test_frontend_static.py` |
| Job names auto-generated (YYMMDD-001 format) | Implemented and tested | `tests/test_batching.py` |
| Presets configured: Ortho/Hollow/Die = lay flat; Tooth = auto-supports; All = Precision Model Resin 100µm | Implemented and repository-verified | UI preset is now translated to a PreFormServer preset hint |
| PreFormServer handoff creates scene, imports STLs, configures presets, validates layout, sends to printer | Implemented and repository-verified | Includes per-file preset hint propagation, row and bulk printer routing, auto-layout validation, and whole-case rollback |
| Print Queue tab displays jobs with screenshots, names, cases, status | Implemented and tested | `tests/test_print_queue.py`, `tests/test_print_queue_polling.py` |
| Formlabs Web API client authenticates and fetches job data | Implemented and tested | `tests/test_formlabs_web_client.py` |
| Backend polls Formlabs API every 5s for status updates | Partially complete | Current design uses frontend 5s polling plus backend cache-on-request sync |
| Status values shown: Queued, Printing, Failed, Paused, Completed | Implemented | Schema/UI support present |
| Connection errors handled with user-friendly messages | Basic handling implemented | Broader recovery remains a stabilization task |
| All P0 tests passing | Complete | Full suite currently passes in this environment (`250 passed`); TypeScript and affected Playwright bulk-actions checks pass |

---

## Phase 2: Enhanced Queue Features 🔲 PARTIALLY IMPLEMENTED

### Goal

Production-ready queue management with UX improvements.

### Current Status (2026-04-21)

Several items originally listed for Phase 2 are already present in the repository:

- undo removal (currently 10s rather than the earlier roadmap's 30s wording)
- 3D preview modal
- queue polling
- case-aware selection
- status legend filters

This phase should now be treated as a refinement/stabilization phase rather than untouched planned work.

### Scope

| Feature | Description | Effort | Priority |
|---------|-------------|--------|----------|
| Undo removal (30s window) | Allow undo after row deletion | 1 day | P1 |
| Locking UI | Simulated lock during editing | 0.5 day | P2 |
| 3D preview modal | Interactive STL viewer (Three.js) | 2-3 days | P1 |
| Real-time polling | Auto-refresh queue (5-10s) | 0.5 day | P1 |
| Case-aware selection | Auto-select same case ID rows | 1 day | P1 |
| Legend filters | Clickable status filter | 0.5 day | P2 |

### Files to Modify

- `andent_web/app/static/app.js` (major updates)
- `andent_web/app/static/index.html` (preview modal)
- `andent_web/app/static/styles.css` (lock/filter styling)

### Test Plan

| Test | Description |
|------|-------------|
| `test_undo_removal` | Undo countdown and restore |
| `test_3d_preview` | Three.js renders STL |
| `test_polling` | Auto-refresh works |
| `test_case_selection` | Case-aware auto-select |
| `test_legend_filter` | Status filter works |

### Exit Criteria

- Undo removal works with countdown feedback
- 3D preview renders STL in modal
- Auto-refresh updates queue every 5-10s
- Case-aware selection auto-selects related rows
- Legend filters rows by status

### Estimated: 5-6 days

---

## Phase 3: Validation & Metrics 🔲 PARTIALLY IMPLEMENTED

### Goal

Prove classification accuracy meets targets, add metrics dashboard.

### Current Status (2026-04-21)

Metrics scaffolding already exists in the repository (`app/services/metrics.py`, `app/routers/metrics.py`, tests), but it is not yet wired to live workflow events strongly enough to prove launch readiness.

### Scope

| Feature | Description | Effort | Priority |
|---------|-------------|--------|----------|
| Accuracy testing | Test against representative STL dataset | 1-2 days | P0 |
| Metrics dashboard | Straight-through %, review % counters | 1-2 days | P1 |
| Edge case handling | Low-confidence, ambiguous case IDs | 1 day | P1 |
| Classification report | Summary report generation | 1 day | P2 |

### Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Straight-through classification | ≥95% | `Ready` without human edit |
| Human review rate | ≤2% | `Needs Review` or `Check` status |
| Classification latency | <30s | Upload to table render |

### Files to Create

- `andent_web/app/services/metrics.py` (new)
- `andent_web/app/routers/metrics.py` (new)
- Test data in `Andent/04_customer-facing/`

### Test Plan

| Test | Description |
|------|-------------|
| `test_accuracy_dataset` | Run against sample STLs |
| `test_metrics_calculation` | Verify metric formulas |
| `test_edge_cases` | Low-confidence handling |

### Exit Criteria

- ≥95% straight-through on test dataset
- ≤2% human review rate
- Metrics visible in UI
- Edge cases documented

### Estimated: 3-4 days

---

## Phase 4: Production Hardening 🔲 PARTIALLY IMPLEMENTED

### Goal

Deployment-ready system for dental lab use.

### Current Status (2026-04-21)

Some Phase 4 basics already exist, including health endpoints and network-binding support. The remaining work is broader hardening, operational validation, and documentation rather than a true zero-start phase.

### Scope

| Feature | Description | Effort | Priority |
|---------|-------------|--------|----------|
| Error recovery | Graceful failure handling | 1-2 days | P0 |
| Structured logging | Debug-friendly logs | 1 day | P1 |
| Health checks | Server + PreFormServer status | 0.5 day | P0 |
| User documentation | Guide for operators | 1 day | P1 |
| Run script | Easy start/stop | 0.5 day | P0 |
| Network binding | LAN access (not localhost only) | 0.5 day | P0 |

### Files to Create/Modify

- `andent_web/app/main.py` (health endpoint)
- `andent_web/app/config.py` (network binding)
- `run_andent_web.py` (new - startup script)
- `docs/deployment-guide.md` (new)
- `docs/user-guide.md` (new)

### Test Plan

| Test | Description |
|------|-------------|
| `test_health_endpoint` | Health check works |
| `test_network_access` | LAN connection works |
| `test_error_recovery` | Graceful failure handling |
| `test_logging` | Structured log output |

### Exit Criteria

- Server accessible from LAN
- Health endpoint works
- User documentation complete
- Easy start/stop script

### Estimated: 3-4 days

---

## Removed Scope (PreFormServer Handles)

The following were removed from Andent Web scope after architecture clarification:

| Feature | Owner |
|---------|-------|
| Orient & pack | PreFormServer |
| Support generation | PreFormServer |
| Job queue management | PreFormServer + Formlabs Dashboard |
| Printer dispatch | PreFormServer |
| Print status tracking | Formlabs Web API |
| Printer-group routing | PreFormServer |

---

## Timeline Summary

| Phase | Days | Cumulative |
|-------|------|------------|
| Phase 0 (done) | — | 0 |
| Phase 1 | 8 | 8 days |
| Phase 2 | 5-6 | 13-14 days |
| Phase 3 | 3-4 | 16-18 days |
| Phase 4 | 3-4 | 19-22 days |

**Historical estimate:** ~19-22 days from the original 2026-04-18 planning point. This is no longer an authoritative remaining-effort forecast.

---

## Next Action

**Live acceptance proof**

1. Run a live PreFormServer/Formlabs validation pass.
2. Capture real workflow metrics for launch acceptance.
3. Record the operational evidence in the planning docs.

---

## Open Gaps — Deferred to Phase 3

| Gap | Status |
|-----|--------|
| Upload-to-queue latency target | Defined: <30s per file |
| Printer dispatch success-rate target | To be defined |
| Mixed-model-type upload handling rules | Compatible same-printer-group/material/layer-height presets are handled by Form 4B/Form 4BL build manifests; incompatible case-level mixes route to review |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-18 | Created roadmap with revised phases |
| 2026-04-18 | Removed PreFormServer scope from Andent Web |
| 2026-04-18 | Marked Phase 0 complete |
| 2026-04-20 | Phase 1 requirements finalized with Print Queue tab, Formlabs Web API integration, batching logic, and preset configuration |
| 2026-04-21 | Updated roadmap to reflect implemented Phase 1/2/3/4 surfaces and remaining verification gaps |
| 2026-04-21 | Updated after stabilization pass: clean full-suite verification, classify-route fix, preset/device propagation completed |
| 2026-04-21 | Updated after Form 4BL build layout completion: build manifests, mixed-compatible preset grouping, and 187-test verification |
| 2026-04-23 | Updated after printer-aware planner enhancement: XY budgets now scale by printer, startup-case seeding is explicit, and filler fallback is locked by tests |
| 2026-04-27 | Marked preset/printer/holding policy complete: Form 4B/Form 4BL manifests, printer-group edits, density holding, Release now, 250-test verification, TypeScript, and affected Playwright bulk-actions release gate |

---

## References

- Architecture: `Andent/02_planning/02_Architecture-andent-web.md`
- PreFormServer Handoff: `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
- Requirements PRD: `Andent/01_requirements/prd-andent-web-auto-prep.md`
- Planning PRD: `Andent/02_planning/01_PRD-andent-web.md`
