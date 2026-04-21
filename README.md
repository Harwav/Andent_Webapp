# Andent Webapp

Standalone Andent web application for browser-based dental workflow automation.

## Overview

Andent Web provides a modern web interface for dental case intake, STL classification, and PreFormServer handoff. It accepts STL uploads, automatically classifies model types (Ortho, Die, Tooth, Splint), plans compatibility-aware Form 4BL builds, and preserves per-file preset hints for downstream processing.

**Current Repository Scope:**
- Browser-based STL upload
- Per-file classification table
- Session-scoped Model Type and Preset edits
- Queue management and batch operations
- Compatibility-aware Form 4BL build planning
- PreFormServer handoff and print queue tracking

## Quick Start

### Prerequisites

- Python 3.9+
- pip or uv

### Installation

```bash
# Clone the repository
git clone https://github.com/Harwav/Andent_Webapp.git
cd Andent_Webapp

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Run Locally

```bash
# From the repository root
uvicorn app.main:app --reload --port 8090
```

Open in browser:
```
http://localhost:8090/
```

### Health Checks

```bash
curl http://localhost:8090/health
curl http://localhost:8090/health/live
curl http://localhost:8090/health/ready
```

## Project Structure

```
Andent_Webapp/
├── app/                       # FastAPI web application
│   ├── main.py                # Application entry point
│   ├── config.py              # Settings and configuration
│   ├── database.py            # SQLite database layer
│   ├── schemas.py             # Pydantic models
│   ├── routers/
│   │   ├── uploads.py         # Upload and classification endpoints
│   │   └── metrics.py         # Metrics dashboard
│   ├── services/
│   │   ├── classification.py  # STL classification logic
│   │   ├── preset_catalog.py   # Preset compatibility metadata
│   │   ├── build_planning.py   # Form 4BL build manifest planning
│   │   ├── planning_preview.py # Build preview logic
│   │   ├── preform_client.py   # PreFormServer local API client
│   │   ├── print_queue_service.py # Print handoff and queue sync
│   │   └── prep_pipeline.py    # Prep pipeline utilities
│   └── static/                # Frontend assets
├── core/                      # Shared backend modules
│   ├── andent_classification.py  # Case ID and artifact classification
│   ├── batch_optimizer.py        # STL dimension/volume utilities
│   ├── stl_validator.py          # STL file validation
│   ├── andent_service_pipeline.py # Prep pipeline orchestration
│   ├── andent_planning.py        # Build planning logic
│   ├── fps_parser.py             # FPS file parser
│   └── constants.py              # App constants
├── tests/                     # Test suite
├── Andent/                    # Product documentation
│   ├── 00_context/
│   ├── 01_requirements/
│   └── 02_planning/
├── requirements.txt
└── README.md
```

## API Endpoints

### Uploads

- `POST /api/uploads/classify` - Upload and classify STL files
- `GET /api/uploads/queue` - List queue rows
- `PATCH /api/uploads/rows/{row_id}` - Update classification
- `POST /api/uploads/rows/bulk-update` - Bulk update classifications
- `POST /api/uploads/rows/send-to-print` - Send ready rows to PreFormServer using build manifests
- `POST /api/uploads/rows/bulk-delete` - Delete rows
- `GET /api/uploads/rows/{row_id}/file` - Download STL file
- `GET /api/uploads/rows/{row_id}/thumbnail.svg` - Get thumbnail SVG
- `GET /api/uploads/rows/{row_id}/plan-preview` - Get case plan preview
- `POST /api/uploads/rows/batch-plan-preview` - Batch plan preview
- `GET /api/print-queue/jobs` - List tracked print jobs
- `GET /api/print-queue/jobs/{job_id}/screenshot` - Fetch cached or remote job screenshot

### System

- `GET /health` - Health check with timestamp
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /metrics` - Metrics dashboard (HTML)

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANDENT_WEB_HOST` | `127.0.0.1` | Server host |
| `ANDENT_WEB_PORT` | `8090` | Server port |
| `ANDENT_WEB_DATA_DIR` | `./data` | Data directory |
| `ANDENT_WEB_DATABASE_PATH` | `./data/andent_web.db` | Database path |

## Testing

```bash
# Run tests from repository root
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q
```

## Release Gate

```bash
npm install
npx playwright install chromium
npm run test:release-gate
```

Prerequisite: a live compatible PreFormServer is reachable at `http://localhost:44388` for the happy-path scenarios.

## Roadmap

### Current Repository State
- [x] STL upload and classification
- [x] Manual model type/preset overrides
- [x] Queue management
- [x] Batch operations
- [x] Compatibility-aware Form 4BL build manifests
- [x] Real PreFormServer handoff path
- [x] Print Queue tab and job status polling
- [ ] Live PreFormServer/Formlabs acceptance validation

## Development

See `Andent/02_planning/` for product documentation:
- [PRD](Andent/02_planning/01_PRD-andent-web.md)
- [Architecture](Andent/02_planning/02_Architecture-andent-web.md)
- [PreFormServer Handoff](Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md)
- [Implementation Roadmap](Andent/02_planning/04_Roadmap-implementation.md)

## License

Proprietary - FormFlow Dent Project

## Support

Contact your Formlabs representative for technical support.
