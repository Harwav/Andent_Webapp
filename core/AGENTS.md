# Core Module

## OVERVIEW

Shared backend utilities - classification, planning, validation, parsing. Reusable across projects.

## STRUCTURE

```
core/
├── andent_classification.py   # Case ID and artifact classification
├── andent_planning.py         # Build planning logic
├── andent_service_pipeline.py # Prep pipeline orchestration
├── batch_optimizer.py         # STL dimension/volume batch packing
├── constants.py               # App-wide constants
├── fps_parser.py              # FPS file parser
└── stl_validator.py           # STL file validation utilities
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Classification logic | `andent_classification.py` | Case/artifact type detection |
| Planning algorithms | `andent_planning.py` | Build planning rules |
| Pipeline orchestration | `andent_service_pipeline.py` | Multi-step workflow |
| Batch optimization | `batch_optimizer.py` | Dimension calculations |
| FPS parsing | `fps_parser.py` | **DO NOT override layer thickness** (line 127) |
| STL validation | `stl_validator.py` | File format validation |

## CONVENTIONS

- **Stateless utilities**: Pure functions, no side effects
- **Constants module**: Centralized app constants in `constants.py`
- **Type hints**: Full type annotations on all functions
- **Docstrings**: Google-style or NumPy-style docstrings

## ANTI-PATTERNS

- **DO NOT override layer thickness** in `fps_parser.py:127` - may be incorrect
- **No app dependencies**: Core should not import from `app/`
- **No database access**: Core is data/algorithm layer only
- **No HTTP logic**: No FastAPI, no requests, no network calls

## UNIQUE STYLES

- **Phase-aligned**: Some modules prepared for Phase 1+ features
- **Reusable design**: Core modules designed for potential extraction to separate package

## NOTES

- **Import pattern**: `from core import module_name` or `from core.module import function`
- **Test coverage**: All core modules should have corresponding tests in `tests/`
