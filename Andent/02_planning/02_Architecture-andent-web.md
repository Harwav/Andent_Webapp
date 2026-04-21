# Architecture: Andent Web Auto Prep

> **Created:** 2026-04-18
> **Updated:** 2026-04-21
> **Status:** Approved intent; repository implementation is complete and automated verification is green, with live-service acceptance still pending

---

## 1. System Overview

Andent Web is a browser-based STL intake and classification system for dental 3D printing. It handles the **preparation phase** before handing off to PreFormServer for actual print processing.

### Key Insight
**PreFormServer handles all print-related operations:** job queue management, printer dispatch, orient/pack, support generation, and print status tracking. Andent Web focuses solely on intake, classification, and handoff.

### Current Repository Snapshot (2026-04-21)

- Implemented: intake/classification queue, editable overrides, send-to-print handoff route, print job persistence, Print Queue tab, Formlabs polling, screenshot retrieval, and plan preview endpoints.
- Verified in repository: the upload/classification route, handoff route, print-queue flows, and a clean full-suite pytest run (`150 passed, 3 skipped` with plugin autoload disabled in this environment).
- Still not proven from repository-only evidence: launch metrics against real workflow volume, and a live external-service run through PreFormServer/Formlabs hardware/cloud.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     ANDENT WEB ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     HTTP      ┌────────────────────────────┐ │
│  │   Browser    │──────────────▶│     Andent Web Backend     │ │
│  │  (Frontend)  │◀──────────────│     (FastAPI)              │ │
│  │              │   JSON API    │                            │ │
│  │  - Upload STL│               │  ANDENT WEB SCOPE:         │ │
│  │  - Classify  │               │  ✅ Upload pipeline        │ │
│  │  - Assign    │               │  ✅ Classification         │ │
│  │    preset    │               │  ✅ Model type detection   │ │
│  │  - Review    │               │  ✅ Case ID extraction     │ │
│  │  - Send to   │               │  ✅ Queue UI + editing     │ │
│  │    PreForm   │               │  ✅ Send prepared job      │ │
│  └──────────────┘               │    to PreFormServer        │ │
│                                 │                            │ │
│                                 │  NOT ANDENT WEB SCOPE:     │ │
│                                 │  ❌ Job queue management  │ │
│                                 │  ❌ Printer dispatch      │ │
│                                 │  ❌ Print status tracking │ │
│                                 │  ❌ Orient/pack           │ │
│                                 │  ❌ Support generation    │ │
│                                 └────────────────────────────┘ │
│                                            │                   │
│                                            │ POST prepared job │
│                                            ▼                   │
│                                 ┌────────────────────────────┐ │
│                                 │     PreFormServer API      │ │
│                                 │     (Formlabs handles)     │ │
│                                 │                            │ │
│                                 │  ✅ Orient & pack          │ │
│                                 │  ✅ Support generation     │ │
│                                 │  ✅ Job queue management   │ │
│                                 │  ✅ Printer dispatch       │ │
│                                 │  ✅ Print status tracking  │ │
│                                 └────────────────────────────┘ │
│                                            │                   │
│                                            ▼                   │
│                                 ┌────────────────────────────┐ │
│                                 │     Formlabs Printers      │ │
│                                 │     (Form 3/4 series)      │ │
│                                 └────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Deployment Pattern

### Local Server Architecture (like YF_ERP)

```
┌─────────────────────────────────────────────────────────┐
│                    LOCAL SERVER                          │
│  (Mac/PC connected to Formlabs printers via USB)        │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │ Andent Web      │  │ PreFormServer   │               │
│  │ (FastAPI:8090)  │←→│ API             │               │
│  └─────────────────┘  └─────────────────┘               │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ SQLite DB       │                                    │
│  │ + STL Storage   │                                    │
│  └─────────────────┘                                    │
└─────────────────────────────────────────────────────────┘
           │
           │ HTTP (局域网)
           ▼
┌─────────────────────────────────────────────────────────┐
│  OTHER COMPUTERS (Dental Lab Workstations)              │
│                                                          │
│  Browser → http://192.168.x.x:8090                      │
│  ↓                                                       │
│  Upload STL → Server processes → Queue updates          │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | Vanilla JS + HTML | Already built in Phase 0, no build step, easy debugging |
| **Backend** | FastAPI | Already built, async-friendly, Python ecosystem |
| **Database** | SQLite | Already built, sufficient for local deployment |
| **Real-time Updates** | HTTP Polling (5-10s) | Simple, reliable, sufficient for queue status |
| **Printer API** | PreFormServer | Existing Formlabs infrastructure |
| **Classification** | `andent_classification.py` | Reuse existing logic |

---

## 5. Responsibility Matrix

### Andent Web Handles

| Task | Description | Status |
|------|-------------|--------|
| STL Upload | Browser drag-drop upload to server | ✅ Phase 0 |
| Classification | Detect model type + case ID from filename/geometry | ✅ Phase 0 |
| Preset Assignment | Map model type to preset | ✅ Phase 0 |
| Queue UI | Active/Processed tabs with editing | ✅ Phase 0 |
| Plan Preview | Read-only predicted grouping and job name preview | Implemented |
| Print Queue Display | Job list, screenshots, and status display via polling | Implemented (display only) |
| Human Review | Override model type/preset for low-confidence cases | ✅ Phase 0 |
| Send to PreFormServer | API call with prepared job data | Implemented and repository-verified |

### PreFormServer Handles (NOT Andent Web)

| Task | Description | Owner |
|------|-------------|-------|
| Orient & Pack | Automatic build plate optimization | PreFormServer |
| Support Generation | AI-powered supports for Die/Tooth | PreFormServer |
| Job Queue Management | Queue jobs for printing | PreFormServer |
| Printer Dispatch | Send jobs to specific printers | PreFormServer |
| Print Status Tracking | Monitor print progress | PreFormServer |

---

## 6. Model Types (Phase 0)

| Model Type | Description |
|------------|-------------|
| `Ortho - Solid` | Solid orthodontic model |
| `Ortho - Hollow` | Hollowed orthodontic model |
| `Die` | Dental die model |
| `Tooth` | Single tooth model |
| `Splint` | Dental splint |

---

## 7. API Endpoints (Current Repository Surface)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/uploads/classify` | POST | Upload and classify STL files |
| `/api/uploads/queue` | GET | Get queue state (active + processed) |
| `/api/uploads/rows/{id}` | PATCH | Update model type/preset |
| `/api/uploads/rows/allow-duplicate` | POST | Allow duplicate rows |
| `/api/uploads/rows/send-to-print` | POST | Send rows to PreFormServer |
| `/api/uploads/rows/{id}` | DELETE | Remove row from queue |
| `/api/uploads/rows/{id}/file` | GET | Download STL file |
| `/api/uploads/rows/{id}/thumbnail.svg` | GET | Get thumbnail preview |
| `/api/uploads/rows/{id}/plan-preview` | GET | Get predicted grouping/job-name preview for a row |
| `/api/uploads/rows/batch-plan-preview` | POST | Get predicted grouping/job-name preview for multiple rows |
| `/api/print-queue/jobs` | GET | List tracked print jobs with synced status |
| `/api/print-queue/jobs/{job_id}/screenshot` | GET | Fetch or return cached job screenshot |
| `/api/metrics/` | GET | Return metrics summary (not yet wired to live workflow events) |

---

## 8. Success Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Straight-through processing | ≥95% | Auto-classify + preset without human review |
| Human review rate | ≤2% | Only low-confidence or ambiguous case ID |
| Upload latency | < 30s per file | Including classification |
| Queue update refresh | 5-10s polling | UI auto-refresh |

Current state: implementation and automated verification are now in place, but the repository still does not record enough live workflow evidence to claim the production targets are met.

---

## 9. Deferred Features (Phase 2+)

- Authentication / Multi-user
- Manual support editing UI
- Printer-fleet optimization
- Cloud deployment
- WebSocket real-time updates

---

## 10. File Structure

```text
andent_web/
├── app/
│   ├── main.py                  # FastAPI app entry
│   ├── config.py                # Settings
│   ├── database.py              # SQLite operations + print_jobs
│   ├── schemas.py               # Pydantic models
│   ├── routers/
│   │   ├── uploads.py           # Upload/classification/handoff endpoints
│   │   ├── print_queue.py       # Print Queue API endpoints
│   │   └── metrics.py           # Metrics API endpoints
│   ├── services/
│   │   ├── classification.py    # Classification logic
│   │   ├── planning_preview.py  # Read-only plan preview
│   │   ├── preform_client.py    # PreFormServer client
│   │   ├── formlabs_web_client.py # Formlabs Web API client
│   │   ├── print_queue_service.py # Print job sync and screenshot caching
│   │   └── metrics.py           # Metrics calculations
│   └── static/
│       ├── index.html           # Queue + Print Queue UI
│       ├── styles.css
│       ├── app.js
│       └── metrics.html
├── data/
│   ├── andent_web.db            # SQLite database
│   ├── uploads/                 # STL storage
│   └── screenshots/             # Cached print queue screenshots
└── requirements.txt
```

---

## 11. Changelog

| Date | Change |
|------|--------|
| 2026-04-18 | Initial architecture doc - clarified PreFormServer handles dispatch/job management |
| 2026-04-18 | Defined Andent Web scope: upload, classify, review, handoff only |
| 2026-04-21 | Updated implementation snapshot, endpoint surface, and verification status to match the repository |
| 2026-04-21 | Updated after stabilization pass: classify route fixed, handoff boundary completed, full automated suite green |

---

## References

- PRD: `Andent/01_requirements/prd-andent-web-auto-prep.md`
- Planning PRD: `Andent/02_planning/prd-andent-web-auto-prep.md`
- Phase 0 Build: `Andent/02_planning/phase-0-build-today.md`
