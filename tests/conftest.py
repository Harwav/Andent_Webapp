"""Shared test fixtures for all tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import build_planning
from app.schemas import DimensionSummary
from app.services.build_planning import _is_full_arch_dimensions, FULL_ARCH_FACTOR

# Global registry: file_path -> (x, y, model_type)
TEST_STL_DIMS: dict[str, tuple[float, float, str | None]] = {}


def _test_projected_xy_area(stl_path: Path) -> float:
    """Test mock: returns bbox area (with full-arch factor) from registered dims.
    Falls back to real STL parsing for actual files, then to a default value.
    """
    path_str = str(stl_path).replace("\\", "/")
    if path_str in TEST_STL_DIMS:
        x, y, _model_type = TEST_STL_DIMS[path_str]
        area = x * y
        dims = DimensionSummary(x_mm=x, y_mm=y, z_mm=10.0)
        if _is_full_arch_dimensions(dims):
            area *= FULL_ARCH_FACTOR
        return area
    # Try loading actual STL file
    try:
        return _real_projected_xy_area(stl_path)
    except Exception:
        # Default fallback for test files that don't register dimensions
        return 1000.0


def _real_projected_xy_area(stl_path: Path) -> float:
    """Real projected area calculation for actual STL files."""
    import numpy as np
    import stl
    mesh = stl.mesh.Mesh.from_file(str(stl_path))
    vectors = mesh.vectors
    v01 = vectors[:, 1] - vectors[:, 0]
    v02 = vectors[:, 2] - vectors[:, 0]
    cross_z = v01[:, 0] * v02[:, 1] - v01[:, 1] * v02[:, 0]
    return 0.5 * float(__import__("numpy").sum(__import__("numpy").maximum(cross_z, 0.0)))


# Apply mock globally
build_planning.projected_xy_area = _test_projected_xy_area


def register_test_dims(file_path: str | None, x: float, y: float, model_type: str | None = None):
    """Helper for test _row functions to register dimensions for the mock."""
    if file_path:
        TEST_STL_DIMS[str(file_path).replace("\\", "/")] = (x, y, model_type)


@pytest.fixture(autouse=True)
def _clear_test_dims():
    """Clear the test dimensions registry between tests."""
    TEST_STL_DIMS.clear()
    yield
