import pytest

from core.cache import STLCache


def test_cache_stores_dimensions():
    cache = STLCache(max_size=100)
    cache.set_dimensions("test.stl", {"x_mm": 50.0, "y_mm": 40.0, "z_mm": 30.0})
    result = cache.get_dimensions("test.stl")
    assert result == {"x_mm": 50.0, "y_mm": 40.0, "z_mm": 30.0}


def test_cache_miss_returns_none():
    cache = STLCache(max_size=100)
    result = cache.get_dimensions("nonexistent.stl")
    assert result is None


def test_cache_evicts_oldest():
    cache = STLCache(max_size=2)
    cache.set_dimensions("a.stl", {"x_mm": 1.0})
    cache.set_dimensions("b.stl", {"x_mm": 2.0})
    cache.set_dimensions("c.stl", {"x_mm": 3.0})
    assert cache.get_dimensions("a.stl") is None  # Evicted
    assert cache.get_dimensions("b.stl") is not None
    assert cache.get_dimensions("c.stl") is not None
