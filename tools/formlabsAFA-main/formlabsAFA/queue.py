from __future__ import annotations

import bisect
import logging
import os
import time
from collections import deque
from pathlib import Path

logger = logging.getLogger("formlabsAFA.queue")


class ModelQueue:
    def __init__(self, input_dir: Path):
        self._queue: deque[str] = deque()
        self._input_dir = input_dir
        self.last_model_time: float = time.time()

    def _mtime_key(self, filename: str) -> float:
        try:
            return (self._input_dir / filename).stat().st_mtime
        except OSError:
            return 0.0

    def add_model(self, filename: str) -> None:
        if not filename.casefold().endswith(".stl"):
            return
        bisect.insort(self._queue, filename, key=self._mtime_key)
        self.last_model_time = time.time()
        logger.debug("Queued model: %s (queue size: %d)", filename, len(self._queue))

    def add_models(self, filenames: list[str]) -> None:
        stls = [f for f in filenames if f.casefold().endswith(".stl")]
        for f in stls:
            bisect.insort(self._queue, f, key=self._mtime_key)
        if stls:
            self.last_model_time = time.time()
            logger.info("Queued %d models (queue size: %d)", len(stls), len(self._queue))

    def drain_batch(self, batch_size: int) -> list[str]:
        count = min(batch_size, len(self._queue))
        batch = [self._queue.popleft() for _ in range(count)]
        return batch

    def requeue(self, filenames: list[str]) -> None:
        for f in filenames:
            self._queue.appendleft(f)
        if filenames:
            logger.info("Requeued %d models", len(filenames))

    def scan_input_folder(self) -> None:
        try:
            files = os.listdir(self._input_dir)
        except OSError:
            logger.warning("Cannot list input folder: %s", self._input_dir)
            return
        stls = [f for f in files if f.casefold().endswith(".stl")]
        self.add_models(stls)

    @property
    def count(self) -> int:
        return len(self._queue)

    def __len__(self) -> int:
        return len(self._queue)
