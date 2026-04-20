# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-20
**Commit:** [current]
**Branch:** [current]

## OVERVIEW

Andent Web - FastAPI web application for dental case intake and STL classification. Browser-based UI (Vanilla JS) + Python backend with SQLite persistence.

## STRUCTURE

```
Andent_Webapp/
├── app/                       # FastAPI web application (routers, services, static assets)
├── core/                      # Shared backend modules (classification, validation, pipeline)
├── tests/                     # Pytest test suite (phase-aligned TDD)
├── Andent/                    # Product documentation (requirements, planning, validation)
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Start server | `app/main.py` | `uvicorn app.main:app --reload --port 8090` |
| Add API endpoint | `app/routers/` | Uploads, metrics routers |
| Classification logic | `app/services/classification.py` | STL model type detection |
| Core utilities | `core/` | Reusable backend modules |
| Test coverage | `tests/` | Phase-labeled pytest tests |
| Product specs | `Andent/02_planning/` | PRD, architecture, roadmap |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `create_app` | Function | `app/main.py:16` | FastAPI app factory |
| `app` | FastAPI | `app/main.py:64` | Application instance |
| `ClassificationRow` | Pydantic | `app/schemas.py` | Upload row schema |
| `Settings` | Pydantic | `app/config.py` | App configuration |
| `init_db` | Function | `app/database.py` | SQLite initialization |

## CONVENTIONS

- **Phase-labeled tests**: Test files include `"""Phase X: [Description] Tests (TDD)"""` docstrings
- **Test naming**: `test_*.py` files with `test_*` functions
- **Import pattern**: Tests may use `sys.path.insert()` to import from `app/` and `core/`
- **Stubs over mocks**: Prefer `_StubSettings` classes over `unittest.mock` where practical
- **Environment config**: Use `ANDENT_WEB_*` env vars for settings overrides

## ANTI-PATTERNS (THIS PROJECT)

- **DO NOT override layer thickness** from `Core_Scene` in `core/fps_parser.py:127` - may be incorrect
- **No root-level main.py**: Entry point is `app/main.py`, not `./main.py`
- **No CI/CD configs**: No `.github/workflows/`, Dockerfile, or Makefile in repo
- **No linting configs**: No `pyproject.toml`, `.editorconfig`, or ESLint configs
- **SQLite for persistence**: Local-first design, not production multi-tenant DB

## UNIQUE STYLES

- **Documentation-centric**: `Andent/` folder with numbered subdirs (`00_context`, `01_requirements`, `02_planning`, `99_Archive`)
- **Vanilla JS frontend**: No React/Vue/Angular - pure JS + HTML + CSS in `app/static/`
- **Polling-based updates**: HTTP polling (5-10s) instead of WebSocket/SSE
- **Phase-gated scope**: Clear Phase 0/Phase 1+ separation in architecture

## COMMANDS

```bash
# Run server
uvicorn app.main:app --reload --port 8090

# Run tests
pytest tests/

# Health checks
curl http://localhost:8090/health
curl http://localhost:8090/health/live
curl http://localhost:8090/health/ready
```

## NOTES

- **Python 3.9+** required (per `requirements.txt`)
- **Data directory**: Defaults to `./data/` for SQLite DB and uploads
- **Static assets**: Served from `app/static/` (index.html, app.js, styles.css)
- **PreFormServer handoff**: Phase 1+ will integrate with external PreFormServer for print orchestration
