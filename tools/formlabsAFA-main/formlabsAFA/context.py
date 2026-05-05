from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp

from formlabsAFA.config import AppConfig
from formlabsAFA.db import Database
from formlabsAFA.frame_profile import FrameProfile
from formlabsAFA.preform.client import PreFormClient
from formlabsAFA.preform.server import PreFormServer

if TYPE_CHECKING:
    from formlabsAFA.queue import ModelQueue

logger = logging.getLogger("formlabsAFA.context")


@dataclass
class WorkspacePaths:
    base: Path

    @property
    def stl_input(self) -> Path:
        return self.base / "1-stls-input"

    @property
    def stl_completed(self) -> Path:
        return self.base / "2-stls-completed"

    @property
    def stl_failed(self) -> Path:
        return self.base / "2-stls-failed"

    @property
    def batches_to_print(self) -> Path:
        return self.base / "3-batches-to-print"

    @property
    def batches_printed(self) -> Path:
        return self.base / "4-batches-printed"

    @property
    def batches_to_reprocess(self) -> Path:
        return self.base / "5-batches-to-reprocess"

    @property
    def logs(self) -> Path:
        return self.base / "logs"

    def ensure_dirs(self) -> None:
        for attr in (
            "stl_input",
            "stl_completed",
            "stl_failed",
            "batches_to_print",
            "batches_printed",
            "batches_to_reprocess",
            "logs",
        ):
            getattr(self, attr).mkdir(parents=True, exist_ok=True)


class BatchCounter:
    _BATCH_NUMBER_RE = re.compile(r"^b?(?P<num>\d+)")

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def set_initial(self, workspace: WorkspacePaths) -> None:
        highest = 0
        folders = [
            workspace.batches_to_print,
            workspace.batches_printed,
            workspace.batches_to_reprocess,
            workspace.logs,
        ]
        for folder in folders:
            if not folder.is_dir():
                continue
            for name in os.listdir(folder):
                if name.endswith((".form", ".txt", ".log")):
                    match = self._BATCH_NUMBER_RE.search(name)
                    if match:
                        highest = max(highest, int(match.group("num")))
        self._value = highest
        logger.info("Initial batch number: %d", self._value)

    def next(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    @property
    def current(self) -> int:
        return self._value


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    preform_client: PreFormClient
    preform_server: PreFormServer
    frame_profiles: dict[str, FrameProfile]
    session: aiohttp.ClientSession
    workspace: WorkspacePaths
    batch_counter: BatchCounter
    batch_semaphore: asyncio.BoundedSemaphore
    chamfer_tmpdir: tempfile.TemporaryDirectory
    model_queue: Any = None  # Set after construction (ModelQueue)

    @property
    def chamfer_dir(self) -> Path:
        return Path(self.chamfer_tmpdir.name)

    async def shutdown(self) -> None:
        logger.info("Shutting down...")
        await self.session.close()
        self.chamfer_tmpdir.cleanup()
        await self.db.close()
        self.preform_server.stop()
        logger.info("Shutdown complete")
