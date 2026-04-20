# Routers Module

## OVERVIEW

API route handlers - HTTP request/response handling, validation, service layer orchestration.

## STRUCTURE

```
routers/
├── uploads.py             # STL upload, classification, queue CRUD, bulk operations
└── metrics.py             # Metrics dashboard HTML endpoint
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add upload endpoint | `uploads.py` | Queue management, file operations |
| Add dashboard endpoint | `metrics.py` | Returns HTML, not JSON |
| Modify existing route | Both files | Follow FastAPI router pattern |

## CONVENTIONS

- **Router prefix**: `router = APIRouter()` with prefix tags in `main.py`
- **Dependency injection**: Use `Depends()` for settings, db sessions
- **Response types**: JSON for API, `FileResponse` for static HTML
- **Error handling**: Raise `HTTPException` with appropriate status codes

## ANTI-PATTERNS

- **No business logic**: Delegate to `services/` layer
- **No direct DB access**: Use service layer or database helpers
- **No hardcoded paths**: Use `settings` for all paths

## UNIQUE STYLES

- **Bulk operations**: `POST /api/uploads/rows/bulk-update`, `bulk-delete` patterns
- **Download endpoints**: `GET /api/uploads/rows/{row_id}/file` for STL downloads

## NOTES

- **Router registration**: Both routers imported and included in `app/main.py`
- **Uploads router**: Primary API surface - most endpoints live here
