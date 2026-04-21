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

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .formlabs_web_client import FormlabsWebClient

if TYPE_CHECKING:
    from ..config import Settings
    from ..schemas import BuildManifest, ClassificationRow, PrintJob


_job_cache: dict | None = None
_cache_timestamp: datetime | None = None
_screenshot_cache: dict[int, tuple[datetime, bytes]] = {}
CACHE_TTL_SECONDS = 5


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


def generate_job_name(date: datetime, batch_number: int) -> str:
    """Generate job name in YYMMDD-NNN format."""
    date_part = date.strftime("%y%m%d")
    number_part = f"{batch_number:03d}"
    return f"{date_part}-{number_part}"


def _resolve_device_id(rows: list["ClassificationRow"]) -> str:
    explicit_printers = {row.printer for row in rows if row.printer}
    if not explicit_printers:
        return "default"
    if len(explicit_printers) > 1:
        raise ValueError("Rows in the same print batch target different printers.")
    return next(iter(explicit_printers))


def _manifest_preset_summary(manifest: "BuildManifest") -> str:
    if not manifest.preset_names:
        return "Unknown Preset"
    if len(manifest.preset_names) == 1:
        return manifest.preset_names[0]
    return " + ".join(manifest.preset_names)


def _manifest_rows(
    manifest: "BuildManifest",
    row_lookup: dict[int, "ClassificationRow"],
) -> list["ClassificationRow"]:
    rows: list["ClassificationRow"] = []
    seen_row_ids: set[int] = set()

    for group in manifest.import_groups:
        for file_spec in group.files:
            row = row_lookup.get(file_spec.row_id)
            if row is None or file_spec.row_id in seen_row_ids:
                continue
            seen_row_ids.add(file_spec.row_id)
            rows.append(row)

    return rows


def _subset_manifest(
    manifest: "BuildManifest",
    case_ids: list[str],
) -> "BuildManifest":
    case_id_set = set(case_ids)
    import_groups = []
    preset_names: list[str] = []

    for group in manifest.import_groups:
        files = [file_spec for file_spec in group.files if file_spec.case_id in case_id_set]
        if not files:
            continue
        preset_names.extend(file_spec.preset_name for file_spec in files)
        import_groups.append(
            group.model_copy(
                update={
                    "row_ids": [file_spec.row_id for file_spec in files],
                    "files": files,
                }
            )
        )

    return manifest.model_copy(
        update={
            "case_ids": case_ids,
            "preset_names": sorted(set(preset_names)),
            "import_groups": import_groups,
        }
    )


def _validation_errors(validation_result: dict[str, Any]) -> list[str]:
    errors = validation_result.get("errors")
    if not isinstance(errors, list):
        return []
    return [str(error) for error in errors]


def process_print_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    batch_number: int,
) -> dict:
    """Process one planned build manifest for printing."""
    from .preform_client import PreFormClient

    if manifest.planning_status != "planned" or not manifest.import_groups:
        raise ValueError("Cannot process a non-plannable build manifest.")

    job_name = generate_job_name(datetime.now(), batch_number)
    row_lookup = {
        row.row_id: row
        for row in rows
        if row.row_id is not None
    }
    active_case_ids = list(manifest.case_ids)
    if not active_case_ids:
        raise ValueError("Build manifest does not contain any cases.")

    client = PreFormClient(settings.preform_server_url)

    try:
        while active_case_ids:
            active_manifest = _subset_manifest(manifest, active_case_ids)
            active_rows = _manifest_rows(active_manifest, row_lookup)
            if not active_rows:
                raise ValueError("No valid STL files found for manifest")

            patient_id = active_case_ids[0]
            scene_result = client.create_scene(patient_id, job_name)
            scene_id = scene_result.get("scene_id")

            if not scene_id:
                raise Exception("Failed to create scene: no scene_id returned")

            imported_any = False
            for group in active_manifest.import_groups:
                for file_spec in group.files:
                    stl_path = Path(file_spec.file_path)
                    if not stl_path.exists():
                        raise ValueError(f"STL file not found for manifest: {file_spec.file_path}")
                    client.import_model(scene_id, str(stl_path), preset=file_spec.preform_hint)
                    imported_any = True

            if not imported_any:
                raise ValueError("No valid STL files found for manifest")

            client.auto_layout(scene_id)
            validation_result = client.validate_scene(scene_id)
            if validation_result.get("valid", False):
                print_result = client.send_to_printer(scene_id, _resolve_device_id(active_rows))
                return {
                    "job_name": job_name,
                    "scene_id": scene_id,
                    "print_job_id": print_result.get("print_id"),
                    "preset": _manifest_preset_summary(active_manifest),
                    "preset_names": active_manifest.preset_names,
                    "compatibility_key": active_manifest.compatibility_key,
                    "case_ids": active_manifest.case_ids,
                    "manifest": active_manifest,
                    "manifest_json": active_manifest.model_dump(),
                    "status": "Queued",
                    "row_count": len(active_rows),
                    "review_required": False,
                }

            validation_errors = _validation_errors(validation_result)
            if len(active_case_ids) == 1:
                return {
                    "job_name": job_name,
                    "scene_id": scene_id,
                    "print_job_id": None,
                    "preset": _manifest_preset_summary(active_manifest),
                    "preset_names": active_manifest.preset_names,
                    "compatibility_key": active_manifest.compatibility_key,
                    "case_ids": active_manifest.case_ids,
                    "manifest": active_manifest,
                    "manifest_json": active_manifest.model_dump(),
                    "status": "Needs Review",
                    "row_count": len(active_rows),
                    "review_required": True,
                    "error_message": ", ".join(validation_errors) or "scene_validation_failed",
                }

            active_case_ids = active_case_ids[:-1]
    finally:
        client.close()


def send_ready_rows_to_print(
    settings: "Settings",
    row_ids: list[int],
) -> list["ClassificationRow"]:
    """Send Ready rows to print with full PreFormServer handoff."""
    from contextlib import closing

    from ..database import _load_rows_by_ids, _now_iso, connect, get_upload_row_by_id
    from ..schemas import PrintJob
    from .build_planning import plan_build_manifests

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

    manifests = plan_build_manifests(ready_rows)
    if not manifests:
        return rows

    now = _now_iso()
    batch_number = 1
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    rows_by_id = {
        row.row_id: row
        for row in ready_rows
        if row.row_id is not None
    }
    for row in ready_rows:
        if row.case_id:
            rows_by_case.setdefault(row.case_id, []).append(row)

    with closing(connect(settings)) as connection:
        try:
            for manifest in manifests:
                manifest_rows = [
                    row
                    for case_id in manifest.case_ids
                    for row in rows_by_case.get(case_id, [])
                ]
                if not manifest_rows:
                    continue

                if manifest.planning_status != "planned" or not manifest.import_groups:
                    review_reason = (
                        f"Build planning requires manual review: {manifest.non_plannable_reason}"
                    )
                    for row in manifest_rows:
                        connection.execute(
                            """
                            UPDATE upload_rows
                            SET status = 'Needs Review',
                                review_required = 1,
                                review_reason = ?,
                                current_event_at = ?
                            WHERE id = ?
                            """,
                            (review_reason, now, row.row_id),
                        )
                        metadata = json.dumps({
                            "status": "Needs Review",
                            "reason": review_reason,
                            "manifest": manifest.model_dump(),
                        })
                        connection.execute(
                            """
                            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (row.row_id, "manual_review_required", now, metadata),
                        )
                    continue

                result = process_print_manifest(settings, manifest, manifest_rows, batch_number)
                accepted_manifest = result["manifest"]
                accepted_rows = _manifest_rows(accepted_manifest, rows_by_id)

                if result.get("review_required"):
                    review_reason = (
                        "PreForm validation requires manual review: "
                        f"{result.get('error_message') or 'scene_validation_failed'}"
                    )
                    for row in accepted_rows:
                        connection.execute(
                            """
                            UPDATE upload_rows
                            SET status = 'Needs Review',
                                review_required = 1,
                                review_reason = ?,
                                current_event_at = ?
                            WHERE id = ?
                            """,
                            (review_reason, now, row.row_id),
                        )
                        metadata = json.dumps({
                            "status": "Needs Review",
                            "reason": review_reason,
                            "scene_id": result["scene_id"],
                            "manifest": result["manifest_json"],
                        })
                        connection.execute(
                            """
                            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (row.row_id, "manual_review_required", now, metadata),
                        )
                    continue

                print_job = PrintJob(
                    job_name=result["job_name"],
                    scene_id=result["scene_id"],
                    print_job_id=result["print_job_id"],
                    status=result.get("status", "Queued"),
                    preset=result["preset"],
                    preset_names=result.get("preset_names", []),
                    compatibility_key=result.get("compatibility_key"),
                    case_ids=result["case_ids"],
                    manifest_json=result.get("manifest_json"),
                )

                connection.execute(
                    """
                    INSERT INTO print_jobs (
                        job_name,
                        scene_id,
                        print_job_id,
                        status,
                        preset,
                        preset_names_json,
                        compatibility_key,
                        case_ids,
                        manifest_json,
                        created_at,
                        updated_at,
                        screenshot_url,
                        printer_type,
                        resin,
                        layer_height_microns,
                        estimated_completion,
                        error_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        print_job.job_name,
                        print_job.scene_id,
                        print_job.print_job_id,
                        print_job.status,
                        print_job.preset,
                        json.dumps(print_job.preset_names),
                        print_job.compatibility_key,
                        json.dumps(print_job.case_ids),
                        json.dumps(print_job.manifest_json) if print_job.manifest_json is not None else None,
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
                batch_number += 1

                for row in accepted_rows:
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
                        "manifest": result["manifest_json"],
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
