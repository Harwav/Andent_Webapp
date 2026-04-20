"""
Web adapter for HeadlessPipeline. Collects pipeline events into a list
that can be polled by a job-status endpoint.

Note: This module is for future Phase 1+ when prep execution is added.
Currently test-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path for core module imports
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import List, Dict, Any
from core.andent_service_pipeline import (
    HeadlessPipeline, PipelineJobConfig, PipelineResult, NullEventHandler,
)


class WebEventHandler(NullEventHandler):
    """Appends structured events to a caller-owned list for job status tracking."""

    def __init__(self, event_log: List[Dict[str, Any]]):
        self._log = event_log

    def update_status(self, status: str) -> None:
        self._log.append({"type": "status", "message": status})

    def show_error(self, title: str, msg: str) -> None:
        self._log.append({"type": "error", "title": title, "message": msg})

    def show_warning(self, title: str, msg: str) -> None:
        self._log.append({"type": "warning", "title": title, "message": msg})

    def processing_finished(self, processed: int, resin_saved: float, skipped: list, review_count: int = 0) -> None:
        self._log.append({
            "type": "finished",
            "processed": processed,
            "resin_saved_ml": resin_saved,
            "skipped_count": len(skipped),
            "review_count": review_count,
        })

    def show_validation_dialog(self, validation: dict) -> str:
        self._log.append({"type": "validation", "data": validation})
        return "continue"


def collect_events() -> List[Dict[str, Any]]:
    """Returns a fresh event log list to pass to WebEventHandler."""
    return []


def run_prep_job(
    settings_manager,
    api_client,
    local_controller,
    job: PipelineJobConfig,
    license_manager=None,
) -> tuple[PipelineResult, List[Dict[str, Any]]]:
    """
    Synchronous headless run. Returns (result, event_log).
    Intended to be called from a background thread or async executor in FastAPI.
    """
    events = collect_events()
    handler = WebEventHandler(events)
    pipeline = HeadlessPipeline(
        settings_manager=settings_manager,
        api_client=api_client,
        event_handler=handler,
        local_controller=local_controller,
        license_manager=license_manager,
    )
    result = pipeline.run(job)
    return result, events
