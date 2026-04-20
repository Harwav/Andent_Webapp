# Tests Module

## OVERVIEW

Pytest test suite with phase-aligned TDD structure. Mix of unit and integration tests.

## STRUCTURE

```
tests/
├── test_case_selection.py     # Case selection logic tests
├── test_health_endpoints.py   # Phase 4: Health endpoint integration tests
├── test_metrics_service.py    # Phase 3: Metrics service tests
├── test_network_binding.py    # Phase 4: Network binding/env var tests
├── test_planning_preview.py   # Planning preview with tmp_path fixture
├── test_polling.py            # Phase 2: Polling behavior tests
├── test_preform_client.py     # PreFormClient with mocked HTTP
├── test_prep_pipeline.py      # Prep pipeline with stubs
├── test_undo_removal.py       # Phase 2: Undo window logic tests
└── __init__.py                # Test package marker
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add API test | `test_health_endpoints.py` | Use `TestClient` pattern |
| Add service test | `test_metrics_service.py` | Unit test with stubs |
| Add integration test | `test_planning_preview.py` | Use `tmp_path` fixture |
| Mock HTTP calls | `test_preform_client.py` | Use `unittest.mock` |

## CONVENTIONS

- **Phase labeling**: `"""Phase X: [Description] Tests (TDD)"""` docstrings
- **Test naming**: `test_*.py` files, `test_*` functions
- **Import pattern**: `sys.path.insert()` to import from `app/` and `core/`
- **Stubs over mocks**: Prefer `_StubSettings` classes where practical
- **Fixtures**: `tmp_path` for temp DB, `TestClient` for API tests

## ANTI-PATTERNS

- **No test interdependence**: Each test should be isolated
- **No hardcoded paths**: Use `tmp_path` or settings fixtures
- **No skipped tests**: Remove or fix, don't `@pytest.mark.skip`
- **No print debugging**: Use `assert` or proper logging

## UNIQUE STYLES

- **Phase-gated**: Tests aligned with product milestones (Phase 0, 2, 3, 4)
- **Mixed mocking**: Stubs for settings, `unittest.mock` for HTTP
- **Real DB in tests**: Some tests use actual SQLite with temp paths

## COMMANDS

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_health_endpoints.py -v

# Run with coverage (add pytest-cov)
pytest tests/ --cov=app --cov=core
```

## NOTES

- **Python 3.9+**: Tests use modern Python features
- **Test isolation**: Use `tmp_path` fixture for temp databases
- **Environment overrides**: Tests may set `os.environ` for config tests
