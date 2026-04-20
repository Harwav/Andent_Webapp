"""Batch optimizer cache integration tests."""

from core.cache import STLCache
from core import batch_optimizer


class _StubMesh:
    def __init__(self, min_coords=(0.0, 0.0, 0.0), max_coords=(10.0, 20.0, 30.0), volume_mm3=1234.0):
        self.min_ = min_coords
        self.max_ = max_coords
        self._volume_mm3 = volume_mm3

    def get_mass_properties(self):
        return self._volume_mm3, None, None


def test_get_stl_dimensions_cache_hit_returns_same_values(monkeypatch):
    cache = STLCache()
    load_count = {"value": 0}

    class _MeshFactory:
        @staticmethod
        def from_file(file_path):
            load_count["value"] += 1
            return _StubMesh()

    monkeypatch.setattr(batch_optimizer, "NUMPY_STL_AVAILABLE", True)
    monkeypatch.setattr(batch_optimizer, "get_cache", lambda: cache)
    monkeypatch.setattr(batch_optimizer, "mesh", type("_MeshModule", (), {"Mesh": _MeshFactory}))

    first = batch_optimizer.get_stl_dimensions("case.stl")
    second = batch_optimizer.get_stl_dimensions("case.stl")

    assert first == second
    assert load_count["value"] == 1


def test_get_stl_volume_ml_cache_miss_reads_file(monkeypatch):
    cache = STLCache()
    load_count = {"value": 0}

    class _MeshFactory:
        @staticmethod
        def from_file(file_path):
            load_count["value"] += 1
            return _StubMesh(volume_mm3=2500.0)

    monkeypatch.setattr(batch_optimizer, "NUMPY_STL_AVAILABLE", True)
    monkeypatch.setattr(batch_optimizer, "get_cache", lambda: cache)
    monkeypatch.setattr(batch_optimizer, "mesh", type("_MeshModule", (), {"Mesh": _MeshFactory}))

    result = batch_optimizer.get_stl_volume_ml("volume.stl")

    assert result == 2.5
    assert load_count["value"] == 1


def test_get_stl_volume_ml_cache_hit_returns_same_values(monkeypatch):
    cache = STLCache()
    load_count = {"value": 0}

    class _MeshFactory:
        @staticmethod
        def from_file(file_path):
            load_count["value"] += 1
            return _StubMesh(volume_mm3=4321.0)

    monkeypatch.setattr(batch_optimizer, "NUMPY_STL_AVAILABLE", True)
    monkeypatch.setattr(batch_optimizer, "get_cache", lambda: cache)
    monkeypatch.setattr(batch_optimizer, "mesh", type("_MeshModule", (), {"Mesh": _MeshFactory}))

    first = batch_optimizer.get_stl_volume_ml("volume.stl")
    second = batch_optimizer.get_stl_volume_ml("volume.stl")

    assert first == second == 4.321
    assert load_count["value"] == 1
