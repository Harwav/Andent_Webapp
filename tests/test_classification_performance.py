"""Thickness sampling performance and cache tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

import numpy as np
import pytest
from stl import mesh as stl_mesh_module

from core import andent_classification
from core.andent_classification import measure_mesh_thickness_stats
from core.cache import STLCache, clear_cache


T = TypeVar("T")


@pytest.fixture
def benchmark() -> Callable[[Callable[[], T]], T]:
    def _benchmark(func: Callable[[], T]) -> T:
        return func()

    return _benchmark


def _build_box_triangles(size: float = 20.0, subdivisions: int = 2) -> list[list[list[float]]]:
    step = size / subdivisions
    triangles: list[list[list[float]]] = []

    def _add_face(origin: tuple[float, float, float], u_axis: int, v_axis: int, normal_sign: int) -> None:
        for u_index in range(subdivisions):
            for v_index in range(subdivisions):
                corners = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    point = [origin[0], origin[1], origin[2]]
                    point[u_axis] += (u_index + du) * step
                    point[v_axis] += (v_index + dv) * step
                    corners.append(point)
                if normal_sign > 0:
                    triangles.append([corners[0], corners[1], corners[2]])
                    triangles.append([corners[0], corners[2], corners[3]])
                else:
                    triangles.append([corners[0], corners[2], corners[1]])
                    triangles.append([corners[0], corners[3], corners[2]])

    _add_face((0.0, 0.0, 0.0), 0, 1, -1)
    _add_face((0.0, 0.0, size), 0, 1, 1)
    _add_face((0.0, 0.0, 0.0), 0, 2, -1)
    _add_face((0.0, size, 0.0), 0, 2, 1)
    _add_face((0.0, 0.0, 0.0), 1, 2, -1)
    _add_face((size, 0.0, 0.0), 1, 2, 1)
    return triangles


@pytest.fixture
def sample_ortho_stl(tmp_path: Path) -> str:
    stl_path = tmp_path / "sample_ortho.stl"
    triangles = _build_box_triangles(subdivisions=2)
    mesh = stl_mesh_module.Mesh(np.zeros(len(triangles), dtype=stl_mesh_module.Mesh.dtype))
    for index, triangle in enumerate(triangles):
        mesh.vectors[index] = triangle
    mesh.save(str(stl_path))
    return str(stl_path)


def test_adaptive_budget_uses_reduced_floor(sample_ortho_stl: str):
    clear_cache()

    result = measure_mesh_thickness_stats(sample_ortho_stl)

    assert result.sample_count >= 24


def test_thickness_cache_avoids_reloading_mesh(monkeypatch, sample_ortho_stl: str):
    clear_cache()
    cache = STLCache()
    load_count = {"value": 0}
    original_mesh = andent_classification.stl_mesh_module.Mesh

    class _MeshFactory:
        @staticmethod
        def from_file(file_path: str):
            load_count["value"] += 1
            return original_mesh.from_file(file_path)

    monkeypatch.setattr(andent_classification, "get_cache", lambda: cache)
    monkeypatch.setattr(
        andent_classification,
        "stl_mesh_module",
        type("_MeshModule", (), {"Mesh": _MeshFactory}),
    )

    first = measure_mesh_thickness_stats(sample_ortho_stl)
    second = measure_mesh_thickness_stats(sample_ortho_stl)

    assert first.as_dict() == second.as_dict()
    assert load_count["value"] == 1


def test_thickness_sampling_performance(benchmark, sample_ortho_stl: str):
    """Test thickness sampling completes quickly."""

    def sample_thickness():
        clear_cache()
        return measure_mesh_thickness_stats(sample_ortho_stl)

    result = benchmark(sample_thickness)
    assert result.sample_count >= 16


def test_thickness_cache_performance(benchmark, sample_ortho_stl: str):
    """Test cached thickness is fast."""

    measure_mesh_thickness_stats(sample_ortho_stl)

    def cached_thickness():
        return measure_mesh_thickness_stats(sample_ortho_stl)

    result = benchmark(cached_thickness)
    assert result is not None
