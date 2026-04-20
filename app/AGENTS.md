# App Module

## OVERVIEW

FastAPI web application layer - routers, services, schemas, static assets. Entry point: `app/main.py`.

## STRUCTURE

```
app/
├── main.py                # App factory, FastAPI instance, route mounting
├── config.py              # Settings class, environment variable parsing
├── database.py            # SQLite initialization, session management
├── schemas.py             # Pydantic models for API requests/responses
├── routers/
│   ├── uploads.py         # STL upload, classification, queue management
│   └── metrics.py         # Metrics dashboard endpoint
├── services/
│   ├── classification.py  # STL model type detection (Ortho/Die/Tooth/Splint)
│   ├── metrics.py         # Dashboard data aggregation
│   ├── planning_preview.py # Case plan preview generation
│   ├── preform_client.py  # PreFormServer HTTP client (Phase 1+)
│   └── prep_pipeline.py   # Prep execution orchestration (Phase 1+)
└── static/
    ├── index.html         # Frontend bootstrap
    ├── app.js             # Vanilla JS application logic
    ├── styles.css         # Application styles
    └── metrics.html       # Metrics dashboard UI
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add endpoint | `routers/uploads.py` or `routers/metrics.py` | Register in `main.py` |
| Modify classification | `services/classification.py` | Model type detection logic |
| Add schema | `schemas.py` | Pydantic models for validation |
| Change config | `config.py` | `Settings` class, env var overrides |
| Frontend changes | `static/` | Vanilla JS, no build step |

## CONVENTIONS

- **Router pattern**: Each router exports `router = APIRouter()` with prefixed routes
- **Service layer**: Business logic in `services/`, not in routers
- **Dependency injection**: `get_settings()` for config, `get_db()` for sessions
- **Static mounting**: `/static` path mounted in `main.py`, served at root `/`

## ANTI-PATTERNS

- **No circular imports**: `main.py` imports routers, routers import services - never reverse
- **No business logic in routers**: Routers handle HTTP, services handle logic
- **No hardcoded paths**: Use `settings` for data_dir, database_path, static_dir

## UNIQUE STYLES

- **Vanilla frontend**: No bundler, no framework - direct JS/CSS in `static/`
- **Polling UI**: Frontend polls every 5-10s for queue updates
- **Phase 0 scope**: Upload/classification only, no real PreFormServer handoff yet

## COMMANDS

```bash
# Run server from repo root
uvicorn app.main:app --reload --port 8090

# Test specific endpoint
curl http://localhost:8090/health
curl http://localhost:8090/api/uploads/queue
```

## NOTES

- **Entry point**: `uvicorn app.main:app` - note `app.main:app` syntax
- **Settings overrides**: `ANDENT_WEB_HOST`, `ANDENT_WEB_PORT`, `ANDENT_WEB_DATA_DIR`
- **Database**: SQLite at `./data/andent_web.db` by default
