"""STL analysis cache for expensive STL computations."""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from threading import RLock
from typing import Any, Dict, Optional, TypeVar


T = TypeVar("T")


class STLCache:
    """Thread-safe LRU cache for STL analysis results."""

    def __init__(self, max_size: int = 1000) -> None:
        self.max_size = max_size
        self._dimensions_cache: "OrderedDict[str, Dict[str, float]]" = OrderedDict()
        self._volume_cache: "OrderedDict[str, float]" = OrderedDict()
        self._thickness_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = RLock()

    def _get_file_key(self, file_path: str) -> str:
        """Generate a cache key from file path and modification time."""
        try:
            mtime = os.path.getmtime(file_path)
            key = f"{file_path}:{mtime}"
            return hashlib.md5(key.encode("utf-8")).hexdigest()
        except OSError:
            return file_path

    def _evict_if_needed(self, cache: "OrderedDict[str, T]") -> None:
        """Remove oldest entries if a cache exceeds its maximum size."""
        while len(cache) > self.max_size:
            cache.popitem(last=False)

    def _get(self, cache: "OrderedDict[str, T]", file_path: str) -> Optional[T]:
        """Get a cached value and update recency."""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        return None

    def _set(self, cache: "OrderedDict[str, T]", file_path: str, value: T) -> None:
        """Set a cached value and evict older entries if needed."""
        key = self._get_file_key(file_path)
        with self._lock:
            if key in cache:
                cache.move_to_end(key)
            cache[key] = value
            self._evict_if_needed(cache)

    def get_dimensions(self, file_path: str) -> Optional[Dict[str, float]]:
        """Get cached STL bounding-box dimensions."""
        return self._get(self._dimensions_cache, file_path)

    def set_dimensions(self, file_path: str, dimensions: Dict[str, float]) -> None:
        """Cache STL bounding-box dimensions."""
        self._set(self._dimensions_cache, file_path, dimensions)

    def get_volume(self, file_path: str) -> Optional[float]:
        """Get cached STL volume."""
        return self._get(self._volume_cache, file_path)

    def set_volume(self, file_path: str, volume_ml: float) -> None:
        """Cache STL volume."""
        self._set(self._volume_cache, file_path, volume_ml)

    def get_thickness(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get cached STL thickness statistics."""
        return self._get(self._thickness_cache, file_path)

    def set_thickness(self, file_path: str, thickness_stats: Dict[str, Any]) -> None:
        """Cache STL thickness statistics."""
        self._set(self._thickness_cache, file_path, thickness_stats)

    def clear(self) -> None:
        """Clear all cache buckets."""
        with self._lock:
            self._dimensions_cache.clear()
            self._volume_cache.clear()
            self._thickness_cache.clear()


_stl_cache: Optional[STLCache] = None


def get_cache() -> STLCache:
    """Get or create the global STL cache instance."""
    global _stl_cache
    if _stl_cache is None:
        _stl_cache = STLCache(max_size=1000)
    return _stl_cache


def clear_cache() -> None:
    """Clear the global STL cache instance if present."""
    global _stl_cache
    if _stl_cache is not None:
        _stl_cache.clear()
