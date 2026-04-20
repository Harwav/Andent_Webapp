# Andent Webapp

Standalone Andent web application for browser-based dental workflow automation.

## Overview

Andent Web provides a modern web interface for dental case intake and STL classification. It accepts STL uploads, automatically classifies model types (Ortho, Die, Tooth, Splint), and prepares cases for downstream processing.

**Phase 0 Scope:**
- Browser-based STL upload
- Per-file classification table
- Session-scoped Model Type and Preset edits
- Queue management and batch operations

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
│   │   ├── planning_preview.py # Case preview logic
│   │   └── prep_pipeline.py   # Future prep execution (Phase 1+)
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
- `POST /api/uploads/rows/send-to-print` - Mark rows for print dispatch
- `POST /api/uploads/rows/bulk-delete` - Delete rows
- `GET /api/uploads/rows/{row_id}/file` - Download STL file
- `GET /api/uploads/rows/{row_id}/thumbnail.svg` - Get thumbnail SVG
- `GET /api/uploads/rows/{row_id}/plan-preview` - Get case plan preview
- `POST /api/uploads/rows/batch-plan-preview` - Batch plan preview

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
pytest tests/
```

## Roadmap

### Phase 0 (Current)
- [x] STL upload and classification
- [x] Manual model type/preset overrides
- [x] Queue management
- [x] Batch operations
- [ ] Print dispatch integration (simulated)

### Phase 1 (Planned)
- [ ] Real PreFormServer handoff
- [ ] Prep pipeline execution
- [ ] Job status tracking
- [ ] Printer dispatch automation

## Development

See `Andent/02_planning/` for product documentation:
- [PRD](Andent/02_planning/prd-andent-web.md)
- [Architecture](Andent/02_planning/architecture-andent-web.md)
- [Implementation Roadmap](Andent/02_planning/implementation-roadmap.md)

## License

Proprietary - FormFlow Dent Project

## Support

Contact your Formlabs representative for technical support.
