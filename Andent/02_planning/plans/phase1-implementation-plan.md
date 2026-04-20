# Phase 1 Implementation Plan: PreFormServer Handoff + Print Queue

> **Created:** 2026-04-20
> **Status:** Ready for Implementation
> **Duration:** 8 days
> **Dependencies:** Phase 0 Complete

---

## Overview

This plan details the implementation of Phase 1: PreFormServer integration with automated batching and the new Print Queue tab for job monitoring.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PHASE 1 ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐                                                        │
│  │   Browser    │                                                        │
│  │  (Frontend)  │──────┐                                                 │
│  │              │      │ HTTP                                              │
│  └──────────────┘      │                                                 │
│                       ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  Andent Web Backend (FastAPI)                                    │  │
│  │                                                                  │  │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │  │
│  │  │ Uploads Router     │  │ Print Queue      │  │ Database     │   │  │
│  │  │ (batching logic) │  │ Router           │  │ (SQLite)     │   │  │
│  │  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘   │  │
│  │           │                    │                    │          │  │
│  │           ▼                    ▼                    ▼          │  │
│  │  ┌──────────────────┐  ┌──────────────────┐                     │  │
│  │  │ PreFormClient    │  │ FormlabsWeb      │                     │  │
│  │  │ (localhost:44388)│  │ Client           │                     │  │
│  │  └────────┬─────────┘  └────────┬─────────┘                     │  │
│  │           │                      │                              │  │
│  └───────────┼──────────────────────┼──────────────────────────────┘  │
│               │                      │                                 │
│               ▼                      ▼                                 │
│  ┌──────────────────┐  ┌──────────────────┐                           │
│  │ PreFormServer    │  │ Formlabs Web API │                           │
│  │ (Scene/Orient)   │  │ (Status/Images)  │                           │
│  │ localhost:44388  │  │ api.formlabs.com │                           │
│  └──────────────────┘  └──────────────────┘                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Task Breakdown

### Task 1: Update Preset Configuration (0.5 day)
**Goal:** Configure preset mappings per finalized requirements

**Files to Modify:**
- `app/services/classification.py` - Update `default_preset()`

**Changes:**
- Ortho Solid/Hollow: Lay flat, no supports
- Die: Lay flat, no supports
- Tooth: Auto-generate supports
- All: Precision Model Resin, 100µm, Form 4BL

**Acceptance Criteria:**
- [ ] Preset mappings updated
- [ ] Tests pass for all model types

---

### Task 2: Implement Batching Logic (1 day)
**Goal:** Group Ready cases by preset, generate job names

**Files to Create/Modify:**
- `app/services/print_queue_service.py` (new)
- `app/routers/uploads.py` - Replace simulated handoff

**Key Functions:**
```python
def batch_cases_by_preset(rows: List[ClassificationRow]) -> Dict[str, List[ClassificationRow]]
def generate_job_name(date: datetime, batch_number: int) -> str
```

**Rules:**
- Group by preset only (not model type)
- One case cannot span multiple batches
- Job name format: YYMMDD-001 (auto-increment)

**Acceptance Criteria:**
- [ ] Batching groups cases correctly
- [ ] Job names auto-generate with correct format
- [ ] Edge cases handled (duplicate prevention)

---

### Task 3: Real PreFormServer Handoff (1 day)
**Goal:** Replace simulated send-to-print with actual API calls

**Files to Modify:**
- `app/routers/uploads.py` - Update `send_to_print` endpoint
- `app/services/preform_client.py` - Ensure all methods work

**Flow:**
1. Validate selected rows (Ready status)
2. Group by preset (Task 2)
3. For each batch:
   - Create scene via PreFormServer
   - Import all STL files
   - Configure preset (support settings)
   - Send to printer group
4. Update row status to "Submitted"
5. Create print job record

**Acceptance Criteria:**
- [ ] Real PreFormServer API calls work
- [ ] Scenes created, STLs imported
- [ ] Jobs submitted to printer queue
- [ ] Error handling for connection failures

---

### Task 4: Create FormlabsWebClient (1 day)
**Goal:** Implement client for Formlabs Web API

**Files to Create:**
- `app/services/formlabs_web_client.py` (new)

**Required Methods:**
```python
class FormlabsWebClient:
    def __init__(self, api_token: str, base_url: str = "https://api.formlabs.com/v1")
    def list_print_jobs(self) -> List[Dict[str, Any]]
    def get_job_status(self, job_id: str) -> Dict[str, Any]
    def get_job_screenshot(self, job_id: str) -> bytes
    def authenticate(self) -> bool
```

**Authentication:**
- API Token from environment variable
- `Authorization: Token <api_token>` header

**Acceptance Criteria:**
- [ ] Client authenticates successfully
- [ ] Can fetch job list
- [ ] Can fetch job status
- [ ] Error handling for auth failures

---

### Task 5: Database Schema for Print Queue (0.5 day)
**Goal:** Add print_jobs table and update config

**Files to Modify:**
- `app/database.py` - Add print_jobs table
- `app/schemas.py` - Add PrintJob schema
- `app/config.py` - Add FORMLABS_API_TOKEN env var

**print_jobs Table:**
```sql
CREATE TABLE print_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL UNIQUE,  -- YYMMDD-001 format
    scene_id TEXT,                   -- From PreFormServer
    print_job_id TEXT,               -- From Formlabs API
    status TEXT,                     -- Queued, Printing, Failed, Paused, Completed
    preset TEXT NOT NULL,
    case_ids TEXT,                   -- JSON array of case IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    screenshot_url TEXT,
    printer_type TEXT,
    resin TEXT,
    layer_height_microns INTEGER,
    estimated_completion TIMESTAMP,
    error_message TEXT
)
```

**Acceptance Criteria:**
- [ ] Table created on startup
- [ ] PrintJob schema validates correctly
- [ ] Environment variables loaded

---

### Task 6: Print Queue Tab UI (1.5 days)
**Goal:** Create new tab with job cards

**Files to Modify:**
- `app/static/index.html` - Add Print Queue tab
- `app/static/app.js` - Job display logic
- `app/static/styles.css` - Job card styling

**UI Components:**
- Tab: "Print Queue" (beside Active/Processed)
- Job Cards:
  - Screenshot thumbnail (clickable → zoom modal)
  - Job name (YYMMDD-001)
  - Cases list (expandable)
  - Printer type, Resin, Layer height
  - Status badge (colored)
- Pagination (50 jobs per page)
- Auto-refresh (5s polling)

**Acceptance Criteria:**
- [ ] Tab renders correctly
- [ ] Job cards display all fields
- [ ] Click screenshot opens zoom modal
- [ ] Cases expandable/collapsible
- [ ] Status badges color-coded

---

### Task 7: Status Polling Service (1 day)
**Goal:** Backend polls Formlabs API, frontend polls backend

**Files to Create/Modify:**
- `app/services/print_queue_service.py` - Polling logic
- `app/routers/print_queue.py` - API endpoints (new)

**Backend Polling:**
- Every 5 seconds
- Cache results (5s TTL)
- Update database with status changes

**Frontend Polling:**
- Every 5 seconds
- Call `/api/print-queue/jobs` endpoint
- Update UI without full refresh

**API Endpoints:**
```python
@router.get("/api/print-queue/jobs")
async def list_print_jobs()

@router.get("/api/print-queue/jobs/{job_id}/screenshot")
async def get_job_screenshot(job_id: str)
```

**Acceptance Criteria:**
- [ ] Backend polls Formlabs API every 5s
- [ ] Frontend polls backend every 5s
- [ ] Status updates propagate to UI
- [ ] Screenshots fetched and cached

---

### Task 8: Connection Error Handling (0.5 day)
**Goal:** Graceful handling of API failures

**Files to Modify:**
- `app/services/preform_client.py` - Retry logic
- `app/services/formlabs_web_client.py` - Retry logic
- `app/static/app.js` - Error display

**Error Scenarios:**
- PreFormServer unreachable
- Formlabs API auth failure
- Network timeouts
- API rate limiting

**User Feedback:**
- Toast notifications for errors
- Retry button for failed handoffs
- Status indicator (connected/disconnected)

**Acceptance Criteria:**
- [ ] Connection errors caught and logged
- [ ] User-friendly error messages
- [ ] Retry mechanism works
- [ ] Graceful degradation

---

### Task 9: Durable Overrides (0.5 day)
**Goal:** Persist Model Type/Preset edits

**Files to Modify:**
- `app/database.py` - Ensure overrides persisted
- `app/routers/uploads.py` - Verify update logic

**Already Mostly Done:**
- Database already stores model_type and preset
- PATCH endpoint already exists

**Acceptance Criteria:**
- [ ] Overrides persist after browser refresh
- [ ] Overrides persist after server restart
- [ ] Tests verify persistence

---

### Task 10: Integration Testing (0.5 day)
**Goal:** End-to-end test of handoff flow

**Files to Create:**
- `tests/test_print_queue.py`
- `tests/test_batching.py`
- `tests/test_formlabs_web_client.py`

**Test Scenarios:**
- Batch multiple cases
- Send to print → Verify PreFormServer receives
- Poll for status updates
- Screenshot display
- Error recovery

**Acceptance Criteria:**
- [ ] All P0 tests passing
- [ ] Integration test covers full flow
- [ ] Error cases tested

---

## Implementation Order

| Order | Task | Duration | Dependencies |
|-------|------|----------|--------------|
| 1 | Task 1: Preset Configuration | 0.5 day | None |
| 2 | Task 5: Database Schema | 0.5 day | None |
| 3 | Task 2: Batching Logic | 1 day | Task 1 |
| 4 | Task 3: Real Handoff | 1 day | Task 2, Task 5 |
| 5 | Task 4: FormlabsWebClient | 1 day | Task 5 |
| 6 | Task 7: Status Polling | 1 day | Task 4, Task 5 |
| 7 | Task 6: Print Queue UI | 1.5 days | Task 7 |
| 8 | Task 8: Error Handling | 0.5 day | Task 3, Task 4 |
| 9 | Task 9: Durable Overrides | 0.5 day | None |
| 10 | Task 10: Integration Testing | 0.5 day | All |

**Parallel Opportunities:**
- Task 1 + Task 5 can be done in parallel (Day 1)
- Task 4 can start once Task 5 is done
- Task 6 can start once Task 7 backend is ready

---

## Configuration

**New Environment Variables:**

```bash
# PreFormServer (existing)
PREFORM_SERVER_URL=http://localhost:44388

# Formlabs Web API (new)
FORMLABS_API_TOKEN=<your_api_token>
FORMLABS_API_URL=https://api.formlabs.com/v1
```

---

## Acceptance Criteria Summary

### Must Have (P0)
- [ ] Batching groups Ready cases by preset
- [ ] Job names auto-generated (YYMMDD-001)
- [ ] Presets configured correctly (Tooth = supports, others = flat)
- [ ] PreFormServer handoff creates scene, imports STLs, sends to printer
- [ ] Print Queue tab displays jobs with screenshots
- [ ] Formlabs Web API client authenticates and fetches jobs
- [ ] Backend polls Formlabs API every 5s
- [ ] Frontend polls backend every 5s
- [ ] Status values: Queued, Printing, Failed, Paused, Completed

### Should Have (P1)
- [ ] Screenshot zoom modal
- [ ] Connection error handling with user feedback
- [ ] Expandable case lists in job cards

### Nice to Have (P2)
- [ ] Durable override persistence verified
- [ ] Additional error recovery scenarios

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Formlabs API unavailable | Low | High | Mock client for development, graceful error handling |
| PreFormServer API changes | Low | Medium | Version pinning, API contract tests |
| Screenshot fetch slow | Medium | Medium | Caching, lazy loading, placeholder images |
| Database migration issues | Low | Medium | Backup strategy, rollback plan |

---

## References

- Architecture: `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
- Roadmap: `Andent/02_planning/04_Roadmap-implementation.md`
- PRD: `Andent/01_requirements/prd-andent-web.md`

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-20 | Created Phase 1 implementation plan |
