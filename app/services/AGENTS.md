# Services Module

## OVERVIEW

Business logic layer - classification, metrics, pipeline orchestration, external client integrations.

## STRUCTURE

```
services/
├── classification.py      # STL file type detection (Ortho/Die/Tooth/Splint)
├── metrics.py             # Dashboard metrics aggregation
├── planning_preview.py    # Case plan preview generation
├── preform_client.py      # PreFormServer HTTP client (Phase 1+)
└── prep_pipeline.py       # Prep pipeline orchestration (Phase 1+)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Modify classification | `classification.py` | Model type detection rules |
| Add metrics | `metrics.py` | Dashboard data calculations |
| Plan preview logic | `planning_preview.py` | Case preview generation |
| PreFormServer integration | `preform_client.py` | HTTP client for external API |

## CONVENTIONS

- **Pure functions**: Services should be stateless where possible
- **Dependency injection**: Accept `settings`, `db` as parameters, not globals
- **Return types**: Use type hints for all function signatures
- **Error handling**: Raise specific exceptions, let routers handle HTTP responses

## ANTI-PATTERNS

- **No HTTP logic**: Services don't return `Response` objects - return data only
- **No database sessions**: Accept session as parameter, don't create internally
- **No print statements**: Use proper logging if needed (not yet configured)

## NOTES

- **Phase 0**: `classification.py` and `metrics.py` are active
- **Phase 1+**: `preform_client.py` and `prep_pipeline.py` are stubs for future integration
