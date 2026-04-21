"""Print Queue Service - Batching, polling, and job management for Phase 1.

This module provides functionality for:
- Grouping Ready cases by preset
- Generating job names
- Managing print job lifecycle
- Polling the Formlabs Web API for job status
- Fetching and caching screenshots
- PreFormServer handoff
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .formlabs_web_client import FormlabsWebClient

if TYPE_CHECKING:
    from ..config import Settings
    from ..schemas import ClassificationRow, PrintJob


_job_cache: dict | None = None
_cache_timestamp: datetime | None = None
_screenshot_cache: dict[int, tuple[datetime, bytes]] = {}
CACHE_TTL_SECONDS = 5
PREFORM_PRESET_HINTS = {
    "Ortho Solid - Flat, No Supports": "ortho_solid_v1",
    "Ortho Hollow - Flat, No Supports": "ortho_hollow_v1",
    "Die - Flat, No Supports": "die_v1",
    "Tooth - With Supports": "tooth_v1",
    "Splint - Flat, No Supports": "splint_v1",
    "Antagonist Solid - Flat, No Supports": "antagonist_solid_v1",
    "Antagonist Hollow - Flat, No Supports": "antagonist_hollow_v1",
}


def _now() -> datetime:
    return datetime.now()


def _cache_is_fresh(timestamp: datetime | None) -> bool:
    if timestamp is None:
        return False
    return (_now() - timestamp) <= timedelta(seconds=CACHE_TTL_SECONDS)


def cache_jobs(jobs: list[dict]) -> None:
    """Cache print jobs for polling."""
    global _job_cache, _cache_timestamp
    _job_cache = {"jobs": jobs, "timestamp": _now()}
    _cache_timestamp = _job_cache["timestamp"]


def get_cached_jobs() -> list[dict] | None:
    """Get cached print jobs if cache is still valid."""
    global _job_cache, _cache_timestamp

    if _job_cache is None or _cache_timestamp is None:
        return None

    if not _cache_is_fresh(_cache_timestamp):
        return None

    jobs = _job_cache.get("jobs")
    return jobs if isinstance(jobs, list) else None


def _poll_formlabs_api(settings: "Settings") -> list[dict] | None:
    if not settings.formlabs_api_token:
        return None

    client = FormlabsWebClient(
        api_token=settings.formlabs_api_token,
        base_url=settings.formlabs_api_url,
    )
    try:
        return client.list_print_jobs()
    except Exception:
        return None
    finally:
        client.close()


def _sync_api_jobs_to_database(settings: "Settings", api_jobs: list[dict]) -> None:
    from contextlib import closing

    from ..database import connect

    with closing(connect(settings)) as connection:
        for api_job in api_jobs:
            print_job_id = api_job.get("id")
            if not print_job_id:
                continue

            row = connection.execute(
                "SELECT id, status FROM print_jobs WHERE print_job_id = ?",
                (str(print_job_id),),
            ).fetchone()
            if row is None:
                continue

            status = api_job.get("status") or row["status"] or "Queued"
            connection.execute(
                """
                UPDATE print_jobs
                SET status = ?, updated_at = CURRENT_TIMESTAMP,
                    printer_type = COALESCE(?, printer_type),
                    resin = COALESCE(?, resin),
                    layer_height_microns = COALESCE(?, layer_height_microns)
                WHERE id = ?
                """,
                (
                    status,
                    api_job.get("printer"),
                    api_job.get("resin"),
                    api_job.get("layer_height_microns"),
                    row["id"],
                ),
            )

        connection.commit()


def sync_print_jobs(settings: "Settings") -> list["PrintJob"]:
    """Refresh print job statuses from Formlabs and return database rows."""
    from ..database import list_print_jobs as db_list_print_jobs

    if get_cached_jobs() is not None:
        return db_list_print_jobs(settings)

    api_jobs = _poll_formlabs_api(settings)
    if api_jobs is not None:
        cache_jobs(api_jobs)
        _sync_api_jobs_to_database(settings, api_jobs)

    return db_list_print_jobs(settings)


def get_print_job_screenshot(settings: "Settings", job_id: int) -> bytes:
    """Fetch a screenshot for a print job and cache it locally."""
    from ..database import get_print_job_by_id, update_print_job

    cached = _screenshot_cache.get(job_id)
    if cached is not None and _cache_is_fresh(cached[0]):
        return cached[1]

    job = get_print_job_by_id(settings, job_id)
    if job is None:
        raise LookupError("Job not found")

    screenshot_path = Path(job.screenshot_url) if job.screenshot_url else None
    if screenshot_path is not None and screenshot_path.exists():
        screenshot_bytes = screenshot_path.read_bytes()
        _screenshot_cache[job_id] = (_now(), screenshot_bytes)
        return screenshot_bytes

    if not settings.formlabs_api_token:
        raise RuntimeError("Formlabs API not configured")
    if not job.print_job_id:
        raise RuntimeError("Print job is missing a Formlabs job ID")

    client = FormlabsWebClient(
        api_token=settings.formlabs_api_token,
        base_url=settings.formlabs_api_url,
    )
    try:
        screenshot_bytes = client.get_job_screenshot(job.print_job_id)
    finally:
        client.close()

    screenshot_dir = settings.data_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"job_{job_id}.png"
    screenshot_path.write_bytes(screenshot_bytes)
    update_print_job(settings, job_id, screenshot_url=str(screenshot_path))
    _screenshot_cache[job_id] = (_now(), screenshot_bytes)
    return screenshot_bytes


def batch_cases_by_preset(rows: list["ClassificationRow"]) -> dict[str, list["ClassificationRow"]]:
    """Group Ready cases by preset.

    Args:
        rows: List of ClassificationRow objects

    Returns:
        Dict mapping preset name to list of rows with that preset.
        Rows with None preset are excluded.
    """
    batches: dict[str, list["ClassificationRow"]] = {}
    seen_cases: set[tuple[str | int | None, str | None, str | None]] = set()

    for row in rows:
        if row.status != "Ready" or row.preset is None:
            continue
        case_key = (
            row.row_id if row.row_id is not None else row.file_name,
            row.case_id,
            row.preset,
        )
        if case_key in seen_cases:
            continue
        seen_cases.add(case_key)
        if row.preset not in batches:
            batches[row.preset] = []
        batches[row.preset].append(row)

    return batches


def generate_job_name(date: datetime, batch_number: int) -> str:
    """Generate job name in YYMMDD-NNN format."""
    date_part = date.strftime("%y%m%d")
    number_part = f"{batch_number:03d}"
    return f"{date_part}-{number_part}"


def _preform_preset_hint(preset: str | None) -> str | None:
    if preset is None:
        return None
    return PREFORM_PRESET_HINTS.get(preset)


def _resolve_device_id(rows: list["ClassificationRow"]) -> str:
    explicit_printers = {row.printer for row in rows if row.printer}
    if not explicit_printers:
        return "default"
    if len(explicit_printers) > 1:
        raise ValueError("Rows in the same print batch target different printers.")
    return next(iter(explicit_printers))


def process_print_batch(
    settings: "Settings",
    preset: str,
    rows: list["ClassificationRow"],
    batch_number: int,
) -> dict:
    """Process a batch of cases for printing."""
    from .preform_client import PreFormClient

    job_name = generate_job_name(datetime.now(), batch_number)

    case_ids = [r.case_id for r in rows if r.case_id]
    stored_paths = []
    for row in rows:
        if row.row_id:
            from ..database import get_stored_file_path

            path = get_stored_file_path(settings, row.row_id)
            if path:
                stored_paths.append(path)

    if not stored_paths:
        raise ValueError("No valid STL files found for batch")

    client = PreFormClient(settings.preform_server_url)

    try:
        patient_id = case_ids[0] if case_ids else "unknown"
        scene_result = client.create_scene(patient_id, job_name)
        scene_id = scene_result.get("scene_id")
        preset_hint = _preform_preset_hint(preset)

        if not scene_id:
            raise Exception("Failed to create scene: no scene_id returned")

        for stl_path in stored_paths:
            if Path(stl_path).exists():
                client.import_model(scene_id, str(stl_path), preset=preset_hint)

        device_id = _resolve_device_id(rows)
        print_result = client.send_to_printer(scene_id, device_id)
        print_job_id = print_result.get("print_id")

        return {
            "job_name": job_name,
            "scene_id": scene_id,
            "print_job_id": print_job_id,
            "preset": preset,
            "case_ids": case_ids,
            "status": "Queued",
            "row_count": len(rows),
        }
    finally:
        client.close()


def send_ready_rows_to_print(
    settings: "Settings",
    row_ids: list[int],
) -> list["ClassificationRow"]:
    """Send Ready rows to print with full PreFormServer handoff."""
    from contextlib import closing
    import json

    from ..database import _load_rows_by_ids, _now_iso, connect, get_upload_row_by_id
    from ..schemas import PrintJob

    if not row_ids:
        return []

    rows = []
    for row_id in row_ids:
        row = get_upload_row_by_id(settings, row_id)
        if row:
            rows.append(row)

    ready_rows = [r for r in rows if r.status == "Ready"]
    if not ready_rows:
        return rows

    batches = batch_cases_by_preset(ready_rows)
    if not batches:
        return rows

    now = _now_iso()
    batch_number = 1

    with closing(connect(settings)) as connection:
        try:
            for preset, batch_rows in batches.items():
                result = process_print_batch(settings, preset, batch_rows, batch_number)
                batch_number += 1

                case_ids = [row.case_id for row in batch_rows if row.case_id]
                print_job = PrintJob(
                    job_name=result["job_name"],
                    scene_id=result["scene_id"],
                    print_job_id=result["print_job_id"],
                    status=result.get("status", "Queued"),
                    preset=preset,
                    case_ids=case_ids,
                )

                connection.execute(
                    """
                    INSERT INTO print_jobs (
                        job_name,
                        scene_id,
                        print_job_id,
                        status,
                        preset,
                        case_ids,
                        created_at,
                        updated_at,
                        screenshot_url,
                        printer_type,
                        resin,
                        layer_height_microns,
                        estimated_completion,
                        error_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        print_job.job_name,
                        print_job.scene_id,
                        print_job.print_job_id,
                        print_job.status,
                        print_job.preset,
                        json.dumps(print_job.case_ids),
                        now,
                        now,
                        print_job.screenshot_url,
                        print_job.printer_type,
                        print_job.resin,
                        print_job.layer_height_microns,
                        print_job.estimated_completion,
                        print_job.error_message,
                    ),
                )

                for row in batch_rows:
                    connection.execute(
                        """
                        UPDATE upload_rows
                        SET status = 'Submitted', current_event_at = ?
                        WHERE id = ?
                        """,
                        (now, row.row_id),
                    )
                    metadata = json.dumps({
                        "status": "Submitted",
                        "job_name": result["job_name"],
                        "scene_id": result["scene_id"],
                        "print_job_id": result["print_job_id"],
                    })
                    connection.execute(
                        """
                        INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (row.row_id, "submitted", now, metadata),
                    )

            connection.commit()
        except Exception:
            connection.rollback()
            raise

        return _load_rows_by_ids(connection, row_ids)
