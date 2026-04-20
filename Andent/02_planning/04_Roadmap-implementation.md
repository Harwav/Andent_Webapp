# Andent Web: Implementation Roadmap

> **Created:** 2026-04-18
> **Status:** Active
> **Current Phase:** Phase 0 Complete → Phase 1 Next

---

## Overview

This roadmap defines the phased implementation for Andent Web Auto Prep. The scope has been simplified based on architecture clarification: **PreFormServer handles orient/pack, supports, dispatch, and tracking**. Andent Web focuses on intake, classification, and handoff.

---

## Progress Summary

| Phase | Name | Status | Progress |
|-------|------|--------|----------|
| Phase 0 | Classification Intake | ✅ COMPLETE | 100% |
| Phase 1 | PreFormServer Handoff | 🔄 In Progress | ~40% |
| Phase 2 | Enhanced Queue Features | 🔲 Planned | 0% |
| Phase 3 | Validation & Metrics | 🔲 Planned | 0% |
| Phase 4 | Production Hardening | 🔲 Planned | 0% |

**Overall Progress: ~35%**

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
| Bulk send-to-print (simulated) | ✅ | POST `/api/uploads/rows/send-to-print` |
| Allow duplicate action | ✅ | POST `/api/uploads/rows/allow-duplicate` |
| Row removal | ✅ | DELETE `/api/uploads/rows/{id}` |
| **Performance optimization** | ✅ | **>95% auto-classification, <20s/file** |

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

## Phase 1: PreFormServer Handoff 🔄 IN PROGRESS

### Goal

Replace simulated handoff with real PreFormServer API integration, add durable override persistence.

### Scope

| Feature | Description | Effort | Priority |
|---------|-------------|--------|----------|
| PreFormServer API contract | Define what data PreFormServer expects | 1 day | P0 |
| `preform_client.py` | API wrapper for PreFormServer calls | 1 day | P0 |
| Real handoff endpoint | Replace simulated send-to-print | 1 day | P0 |
| Connection error handling | Handle PreFormServer failures gracefully | 1 day | P1 |
| Status sync | Update row status from PreFormServer response | 1 day | P1 |
| Durable overrides | Persist Model Type/Preset edits across sessions | 1-2 days | P1 |

### Achieved So Far

| Feature | Status | Commit |
|---------|--------|--------|
| HeadlessPipeline extracted from ProcessingController | ✅ | fdabf3c |
| PipelineEventHandler added | ✅ | 6fbc170 |
| WebEventHandler + run_prep_job() wired | ✅ | 41c58a9 |
| Bulk update/delete API endpoints | ✅ | b69f85a |
| UI polish pass | ✅ | b69f85a |
| 11 E2E gap tests for session persistence | ✅ | 757705b |
| preform_client.py scaffolded | ✅ | b69f85a |

### Remaining for Phase 1 Completion

- Real PreFormServer API handoff (replace simulated send-to-print)
- Connection error handling with user feedback
- Status sync from PreFormServer response
- Durable override persistence across sessions

### Files to Modify/Create

- `andent_web/app/services/preform_client.py` (new)
- `andent_web/app/routers/uploads.py` (modify)
- `andent_web/app/schemas.py` (add handoff schemas)
- `andent_web/app/database.py` (durable storage)

### Test Plan

| Test | Description |
|------|-------------|
| `test_preform_client_connection` | Verify PreFormServer connection |
| `test_preform_client_handoff` | Test handoff request/response |
| `test_handoff_endpoint` | Integration test for send-to-print |
| `test_connection_failure` | Error handling test |
| `test_durable_override` | Override persistence test |

### Exit Criteria

- PreFormServer API client works
- Real handoff succeeds (PreFormServer accepts job)
- Row status reflects PreFormServer response
- Connection errors handled with user feedback
- Overrides persist after browser refresh/server restart

### Estimated: 5-7 days

---

## Phase 2: Enhanced Queue Features 🔲 PLANNED

### Goal

Production-ready queue management with UX improvements.

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

## Phase 3: Validation & Metrics 🔲 PLANNED

### Goal

Prove classification accuracy meets targets, add metrics dashboard.

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

## Phase 4: Production Hardening 🔲 PLANNED

### Goal

Deployment-ready system for dental lab use.

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
| Job queue management | PreFormServer |
| Printer dispatch | PreFormServer |
| Print status tracking | PreFormServer |
| Printer-group routing | PreFormServer |

---

## Timeline Summary

| Phase | Days | Cumulative |
|-------|------|------------|
| Phase 0 (done) | — | 0 |
| Phase 1 | 5-7 | 5-7 days |
| Phase 2 | 5-6 | 10-13 days |
| Phase 3 | 3-4 | 13-17 days |
| Phase 4 | 3-4 | 16-21 days |

**Total: ~16-21 days from now to production-ready**

---

## Next Action

**Phase 1: PreFormServer Handoff**

1. Define PreFormServer API contract
2. Implement `preform_client.py`
3. Replace simulated send-to-print
4. Add durable override storage
5. Test-driven implementation

---

## Open Gaps — Deferred to Phase 3

These items were flagged as residual risks in the PRD. They are not Phase 1 blockers but must be defined before Phase 3 ships.

| Gap | Status |
|-----|--------|
| Upload-to-queue latency target | Not yet defined |
| Printer dispatch success-rate target | Not yet defined |
| Mixed-model-type upload handling rules | Not yet defined |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-18 | Created roadmap with revised phases |
| 2026-04-18 | Removed PreFormServer scope from Andent Web |
| 2026-04-18 | Marked Phase 0 complete |
| 2026-04-20 | Phase 1 marked In Progress (~40%); partial achievements documented |
| 2026-04-20 | Added Open Gaps section (deferred to Phase 3) |

---

## References

- Architecture: `Andent/02_planning/architecture-andent-web.md`
- Requirements PRD: `Andent/01_requirements/prd-andent-web-auto-prep.md`
- Planning PRD: `Andent/02_planning/prd-andent-web-auto-prep.md`