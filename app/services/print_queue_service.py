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
import logging
import os
import re
import shutil
import struct
import zlib
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .formlabs_web_client import FormlabsWebClient
from .preset_catalog import get_preset_profile
from core.stl_validator import validate_stl_file, ValidationStatus

if TYPE_CHECKING:
    from ..config import Settings
    from ..schemas import BuildManifest, ClassificationRow, FilePrepSpec, PrintJob


_job_cache: dict | None = None
_cache_timestamp: datetime | None = None
_screenshot_cache: dict[int, tuple[datetime, bytes]] = {}
CACHE_TTL_SECONDS = 5
HOLDING_STATUS = "Holding for More Cases"
_held_job_ids_created_this_process: set[int] = set()
DAILY_PRINT_JOB_SEQUENCE_LIMIT = 9999
_SEQUENCE_JOB_NAME_RE = re.compile(r"^(?P<date>\d{6})_(?P<sequence>\d{4})$")


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

    local_jobs = db_list_print_jobs(settings)
    if not local_jobs:
        return local_jobs

    release_due_held_jobs(settings)
    local_jobs = db_list_print_jobs(settings)

    if get_cached_jobs() is not None:
        return local_jobs

    if not any(job.print_job_id for job in local_jobs):
        return local_jobs

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

    # Try local screenshot beside the .form file (saved by process_print_manifest)
    local_screenshot_path = (
        Path(job.form_file_path).with_suffix(".png") if job.form_file_path else None
    )
    if local_screenshot_path is not None and local_screenshot_path.exists():
        screenshot_bytes = local_screenshot_path.read_bytes()
        _screenshot_cache[job_id] = (_now(), screenshot_bytes)
        return screenshot_bytes

    if not settings.formlabs_api_token or not job.print_job_id:
        screenshot_bytes = _generate_print_job_preview_png(job)
        _screenshot_cache[job_id] = (_now(), screenshot_bytes)
        return screenshot_bytes

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
    # Store API endpoint so the browser can fetch via /api/print-queue/jobs/{id}/screenshot
    update_print_job(settings, job_id, screenshot_url=f"/api/print-queue/jobs/{job_id}/screenshot")
    _screenshot_cache[job_id] = (_now(), screenshot_bytes)
    return screenshot_bytes


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def _solid_png(width: int, height: int, rgb: bytes) -> bytearray:
    rows = bytearray()
    for _ in range(height):
        rows.append(0)
        rows.extend(rgb * width)
    return rows


def _encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        header
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(pixels), 9))
        + _png_chunk(b"IEND", b"")
    )


def _draw_rect(
    pixels: bytearray,
    width: int,
    height: int,
    *,
    left: int,
    top: int,
    rect_width: int,
    rect_height: int,
    color: tuple[int, int, int],
) -> None:
    right = max(0, min(width, left + rect_width))
    bottom = max(0, min(height, top + rect_height))
    left = max(0, min(width, left))
    top = max(0, min(height, top))
    for y in range(top, bottom):
        row_start = y * (width * 3 + 1) + 1
        for x in range(left, right):
            index = row_start + x * 3
            pixels[index:index + 3] = bytes(color)


def _generate_print_job_preview_png(job: "PrintJob") -> bytes:
    width = 960
    height = 540
    pixels = _solid_png(width, height, b"\xf8\xfb\xff")
    _draw_rect(
        pixels,
        width,
        height,
        left=80,
        top=50,
        rect_width=800,
        rect_height=400,
        color=(230, 237, 245),
    )

    files = []
    manifest = job.manifest_json or {}
    for group in manifest.get("import_groups", []) if isinstance(manifest, dict) else []:
        if isinstance(group, dict):
            files.extend(file for file in group.get("files", []) if isinstance(file, dict))

    if not files:
        files = [{"xy_footprint_estimate": 2500.0}]

    max_area = max(
        float(file.get("xy_footprint_estimate") or 1200.0)
        for file in files
    )
    slot_width = 800 // max(1, len(files))
    for index, file in enumerate(files):
        area = float(file.get("xy_footprint_estimate") or 1200.0)
        scale = max(0.35, min(1.0, area / max_area))
        model_width = max(70, int(slot_width * 0.65 * scale))
        model_height = max(90, int(230 * scale))
        center_x = 80 + slot_width * index + slot_width // 2
        center_y = 250
        _draw_rect(
            pixels,
            width,
            height,
            left=center_x - model_width // 2,
            top=center_y - model_height // 2,
            rect_width=model_width,
            rect_height=model_height,
            color=(58, 132, 196),
        )
        _draw_rect(
            pixels,
            width,
            height,
            left=center_x - model_width // 2 + 8,
            top=center_y - model_height // 2 + 8,
            rect_width=max(1, model_width - 16),
            rect_height=max(1, model_height - 16),
            color=(116, 178, 224),
        )

    return _encode_png(width, height, pixels)


def _next_daily_sequence_job_name(
    date_part: str,
    existing_names: set[str] | None,
) -> str:
    reserved_names = existing_names or set()
    used_sequences: set[int] = set()

    for name in reserved_names:
        match = _SEQUENCE_JOB_NAME_RE.fullmatch(name)
        if match is None or match.group("date") != date_part:
            continue
        used_sequences.add(int(match.group("sequence")))

    for sequence in range(1, DAILY_PRINT_JOB_SEQUENCE_LIMIT + 1):
        candidate = f"{date_part}_{sequence:04d}"
        if sequence not in used_sequences and candidate not in reserved_names:
            return candidate

    raise RuntimeError("Could not generate a unique daily print job name.")


def generate_job_name(
    date: datetime,
    case_ids: Iterable[str],
    *,
    existing_names: set[str] | None = None,
) -> str:
    """Generate a file-safe YYMMDD_XXXX daily sequence job name.

    case_ids is accepted for call-site compatibility. Case traceability is
    stored separately on PrintJob.case_ids and manifest_json.
    """
    date_part = date.strftime("%y%m%d")
    del case_ids
    return _next_daily_sequence_job_name(date_part, existing_names)


def _existing_job_names_for_date(connection, date: datetime) -> set[str]:
    date_part = date.strftime("%y%m%d")
    rows = connection.execute(
        """
        SELECT job_name
        FROM print_jobs
        WHERE job_name LIKE ?
        """,
        (f"{date_part}_%",),
    ).fetchall()
    return {str(row["job_name"]) for row in rows}


def _generate_unique_job_name_for_manifest(connection, date: datetime, manifest: "BuildManifest") -> str:
    return generate_job_name(
        date,
        _manifest_case_ids_by_file_order(manifest),
        existing_names=_existing_job_names_for_date(connection, date),
    )


def _generate_unique_job_name_for_settings(
    settings: "Settings",
    date: datetime,
    case_ids: Iterable[str],
) -> str:
    from ..database import connect, init_db

    init_db(settings)
    with closing(connect(settings)) as connection:
        return generate_job_name(
            date,
            case_ids,
            existing_names=_existing_job_names_for_date(connection, date),
        )


def _resolve_device_id(rows: list["ClassificationRow"], manifest: "BuildManifest" | None = None) -> str:
    explicit_printers = {
        row.printer
        for row in rows
        if row.printer and row.printer != "Default"
    }
    if not explicit_printers:
        return manifest.printer_group if manifest and manifest.printer_group else "Form 4BL"
    if len(explicit_printers) > 1:
        raise ValueError("Rows in the same print batch target different printers.")
    return next(iter(explicit_printers))


def _device_identifier(device: dict[str, Any]) -> str | None:
    for key in ("id", "device_id", "printer_id", "name"):
        value = device.get(key)
        if value:
            return str(value)
    return None


def _device_identity_text(device: dict[str, Any]) -> str:
    parts = []
    for key in (
        "id",
        "device_id",
        "printer_id",
        "name",
        "type",
        "model",
        "product_name",
        "connection_type",
        "status",
    ):
        value = device.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _is_virtual_device(device: dict[str, Any]) -> bool:
    for key in ("is_virtual", "virtual", "isVirtual"):
        value = device.get(key)
        if isinstance(value, bool):
            return value
    return "virtual" in _device_identity_text(device)


def _normalize_device_list(payload: Any) -> list[Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        devices = payload.get("devices")
        return devices if isinstance(devices, list) else []
    return payload if isinstance(payload, list) else []


def _resolve_virtual_device_id(client, preferred_device_id: str | None = None) -> str:
    devices = _normalize_device_list(client.list_devices())
    if not isinstance(devices, list):
        raise RuntimeError("PreFormServer did not return a printer device list.")

    virtual_devices: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        if not _is_virtual_device(device):
            continue
        virtual_devices.append(device)

    if preferred_device_id:
        preferred_text = preferred_device_id.lower()
        for device in virtual_devices:
            device_id = _device_identifier(device)
            if device_id and device_id.lower() == preferred_text:
                return device_id
            if preferred_text in _device_identity_text(device):
                if device_id:
                    return device_id

    for device in virtual_devices:
        device_id = _device_identifier(device)
        if device_id:
            return device_id

    raise RuntimeError(
        "Virtual printer dispatch requires a clearly virtual printer device from PreFormServer."
    )


def _print_id_from_response(response: dict[str, Any]) -> str:
    print_id = response.get("print_id") or response.get("job_id") or response.get("id")
    if not print_id:
        raise RuntimeError("PreFormServer accepted print request without returning a print job ID.")
    return str(print_id)


def _dispatch_scene_if_enabled(
    *,
    client,
    settings: "Settings",
    scene_id: str,
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    job_name: str,
) -> str | None:
    mode = getattr(settings, "print_dispatch_mode", "save_form")
    if mode == "save_form":
        return None
    if mode == "virtual":
        device_id = _resolve_virtual_device_id(client, _resolve_device_id(rows, manifest))
    elif mode == "real":
        device_id = _resolve_device_id(rows, manifest)
    else:
        raise RuntimeError(f"Unsupported print dispatch mode: {mode}")

    response = client.send_to_printer(scene_id, device_id, job_name)
    if not isinstance(response, dict):
        raise RuntimeError("PreFormServer returned an invalid print response.")
    return _print_id_from_response(response)


def _scene_settings_from_manifest(manifest: "BuildManifest") -> dict[str, Any]:
    return {
        "layer_thickness_mm": manifest.layer_thickness_mm or 0.1,
        "machine_type": manifest.machine_type or "FRML-4-0",
        "material_code": manifest.material_code or "FLPMBE01",
        "print_setting": manifest.print_setting or "DEFAULT",
    }


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


def _ordered_manifest_file_specs(manifest: "BuildManifest") -> list["FilePrepSpec"]:
    file_specs = [
        file_spec
        for group in manifest.import_groups
        for file_spec in group.files
    ]
    return sorted(file_specs, key=lambda spec: (spec.order, spec.row_id, spec.file_name))


def _manifest_case_ids_by_file_order(manifest: "BuildManifest") -> list[str]:
    case_ids: list[str] = []
    seen: set[str] = set()

    for file_spec in _ordered_manifest_file_specs(manifest):
        if file_spec.case_id in seen:
            continue
        seen.add(file_spec.case_id)
        case_ids.append(file_spec.case_id)

    for case_id in manifest.case_ids:
        if case_id in seen:
            continue
        seen.add(case_id)
        case_ids.append(case_id)

    return case_ids


def _last_added_case_id(manifest: "BuildManifest") -> str | None:
    ordered_files = _ordered_manifest_file_specs(manifest)
    if ordered_files:
        return ordered_files[-1].case_id
    if manifest.case_ids:
        return manifest.case_ids[-1]
    return None


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


def _form_output_path_from_manifest(settings: "Settings", manifest: "BuildManifest", job_name: str) -> Path:
    output_job_dir = settings.output_dir / job_name
    output_job_dir.mkdir(parents=True, exist_ok=True)
    return output_job_dir / f"{job_name}.form"


def _screenshot_output_path_from_form_path(form_path: Path) -> Path:
    return form_path.with_suffix(".png")


def migrate_print_job_outputs_to_output_dir(settings: "Settings") -> None:
    """Migrate existing .form and .png files to output_dir structure.

    Copies each job's .form and screenshot to output/{job_name}/, then updates
    the DB to point to the new paths and use the API endpoint for screenshot_url.
    """
    from ..database import connect, list_print_jobs, update_print_job

    output_dir = settings.output_dir
    screenshot_dir = settings.data_dir / "screenshots"

    jobs = list_print_jobs(settings)
    migrated = 0
    skipped = 0

    for job in jobs:
        if not job.form_file_path or not job.job_name:
            continue

        old_form_path = Path(job.form_file_path)
        if not old_form_path.exists():
            skipped += 1
            logging.debug("Migration skip: form file missing for job %s", job.job_name)
            continue

        new_job_dir = output_dir / job.job_name
        new_form_path = new_job_dir / f"{job.job_name}.form"
        new_screenshot_path = new_job_dir / f"{job.job_name}.png"

        # Skip if already migrated
        if new_form_path.exists():
            continue

        new_job_dir.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(old_form_path, new_form_path)
        except Exception as exc:
            logging.error("Migration failed to copy form for job %s: %s", job.job_name, exc)
            continue

        # Find screenshot: beside old form, or in screenshots dir
        old_screenshot: Path | None = None
        candidates = [
            old_form_path.with_suffix(".png"),
            screenshot_dir / f"job_{job.id}.png",
        ]
        for candidate in candidates:
            if candidate.exists():
                old_screenshot = candidate
                break

        if old_screenshot:
            try:
                shutil.copy2(old_screenshot, new_screenshot_path)
            except Exception as exc:
                logging.warning("Migration: screenshot copy failed for job %s: %s", job.job_name, exc)

        # Update DB
        try:
            update_print_job(
                settings,
                job.id,
                form_file_path=str(new_form_path),
                screenshot_url=f"/api/print-queue/jobs/{job.id}/screenshot",
            )
            migrated += 1
        except Exception as exc:
            logging.error("Migration: DB update failed for job %s: %s", job.job_name, exc)

    logging.info(
        "Print job output migration complete: %d migrated, %d skipped (no form or already migrated)",
        migrated,
        skipped,
    )


def assert_preform_ready(settings: "Settings") -> None:
    from .preform_setup_service import get_preform_setup_status

    status = get_preform_setup_status(settings)
    if status.readiness != "ready":
        raise ValueError(
            f"PreFormServer setup is required before printing ({status.readiness})."
        )


def process_print_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    batch_number: int,
    job_name: str | None = None,
) -> dict:
    """Process one planned build manifest for printing."""
    from .preform_client import PreFormClient

    if manifest.planning_status != "planned" or not manifest.import_groups:
        raise ValueError("Cannot process a non-plannable build manifest.")

    row_lookup = {
        row.row_id: row
        for row in rows
        if row.row_id is not None
    }
    active_case_ids = _manifest_case_ids_by_file_order(manifest)
    if not active_case_ids:
        raise ValueError("Build manifest does not contain any cases.")
    if job_name is None:
        job_name = _generate_unique_job_name_for_settings(
            settings,
            datetime.now(),
            active_case_ids,
        )
    active_rows = _manifest_rows(manifest, row_lookup)
    if not active_rows:
        raise ValueError("No valid STL files found for manifest")

    client = PreFormClient(settings.preform_server_url)

    try:
        patient_id = active_case_ids[0]
        scene_result = client.create_scene(
            patient_id,
            job_name,
            scene_settings=_scene_settings_from_manifest(manifest),
        )
        scene_id = scene_result.get("scene_id")

        if not scene_id:
            raise Exception("Failed to create scene: no scene_id returned")

        imported_any = False
        support_model_ids: list[str] = []
        failed_cases: set[str] = set()

        # Group files by case_id for case-aware import
        case_files: dict[str, list] = {}
        for file_spec in _ordered_manifest_file_specs(manifest):
            case_id = file_spec.case_id
            if case_id not in case_files:
                case_files[case_id] = []
            case_files[case_id].append(file_spec)

        # Import each case as a unit - if any file in a case fails, block the entire case
        for case_id, file_specs in case_files.items():
            case_failed = False
            for file_spec in file_specs:
                stl_path = Path(file_spec.file_path)
                if not stl_path.exists():
                    logging.error("STL file not found for case %s: %s", case_id, file_spec.file_path)
                    case_failed = True
                    break
                try:
                    import_result = client.import_model(scene_id, str(stl_path), preset=file_spec.preform_hint)
                    profile = get_preset_profile(file_spec.preset_name)
                    if profile is not None and profile.requires_supports:
                        model_id = import_result.get("model_id") or import_result.get("id")
                        if not model_id:
                            logging.error("Support generation requires imported tooth model IDs for: %s (case: %s)", stl_path, case_id)
                            case_failed = True
                            break
                        support_model_ids.append(str(model_id))
                except Exception as exc:
                    logging.error("Failed to import %s (case: %s): %s", stl_path, case_id, exc)
                    case_failed = True
                    break

            if case_failed:
                failed_cases.add(case_id)
                logging.error("Case %s blocked due to import failure", case_id)
            else:
                imported_any = True

        if not imported_any:
            raise ValueError(f"No valid cases could be imported. Failed cases: {sorted(failed_cases)}")

        client.auto_layout(scene_id)
        if support_model_ids:
            client.auto_support(scene_id, models=support_model_ids)
            client.auto_layout(scene_id)
        validation_result = (
            client.validate_scene(scene_id)
            if settings.preform_validation_enabled
            else {"valid": True, "errors": []}
        )
        validation_errors = _validation_errors(validation_result)
        form_path = _form_output_path_from_manifest(settings, manifest, job_name)
        client.save_form(scene_id, form_path)
        form_file_path = str(form_path.resolve())
        # Save screenshot locally for traceability, but don't store local path as screenshot_url.
        # The API endpoint (/api/print-queue/jobs/{id}/screenshot) serves screenshots instead.
        screenshot_path = _screenshot_output_path_from_form_path(form_path)
        try:
            client.save_screenshot(scene_id, screenshot_path)
        except Exception:
            pass  # screenshot unavailable — API endpoint will generate a placeholder
        screenshot_url = None
        print_job_id = _dispatch_scene_if_enabled(
            client=client,
            settings=settings,
            scene_id=scene_id,
            manifest=manifest,
            rows=active_rows,
            job_name=job_name,
        )
        return {
            "job_name": job_name,
            "scene_id": scene_id,
            "print_job_id": print_job_id,
            "form_file_path": form_file_path,
            "screenshot_url": screenshot_url,
            "preset": _manifest_preset_summary(manifest),
            "preset_names": manifest.preset_names,
            "compatibility_key": manifest.compatibility_key,
            "case_ids": active_case_ids,
            "manifest": manifest,
            "manifest_json": manifest.model_dump(),
            "status": "Queued",
            "row_count": len(active_rows),
            "review_required": False,
            "validation_passed": bool(validation_result.get("valid", False)),
            "validation_errors": validation_errors,
            "printer_type": manifest.printer_group,
            "resin": manifest.material_label,
            "layer_height_microns": (
                int(manifest.layer_thickness_mm * 1000)
                if manifest.layer_thickness_mm is not None
                else None
            ),
            "estimated_density": manifest.estimated_density,
        }
    finally:
        client.close()


def _parse_cutoff_today(cutoff_local_time: str, now: datetime) -> datetime:
    try:
        hour_text, minute_text = cutoff_local_time.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError):
        hour = 18
        minute = 0
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _should_hold_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    manifest_index: int,
    final_index_by_compatibility: dict[str | None, int],
    now: datetime,
) -> bool:
    density_target = getattr(settings, "print_hold_density_target", 0.40)
    if density_target <= 0:
        return False
    if manifest.planning_status != "planned" or not manifest.import_groups:
        return False
    if final_index_by_compatibility.get(manifest.compatibility_key) != manifest_index:
        return False
    if manifest.estimated_density >= density_target:
        return False
    cutoff = _parse_cutoff_today(settings.print_hold_cutoff_local_time, now)
    return now < cutoff


def _insert_print_job(
    connection,
    print_job: "PrintJob",
    now: str,
) -> int:
    cursor = connection.execute(
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
            form_file_path,
            printer_type,
            resin,
            layer_height_microns,
            estimated_completion,
            error_message,
            estimated_density,
            density_target,
            hold_cutoff_at,
            hold_reason,
            release_reason,
            released_by_operator,
            validation_passed,
            validation_errors_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            print_job.form_file_path,
            print_job.printer_type,
            print_job.resin,
            print_job.layer_height_microns,
            print_job.estimated_completion,
            print_job.error_message,
            print_job.estimated_density,
            print_job.density_target,
            print_job.hold_cutoff_at,
            print_job.hold_reason,
            print_job.release_reason,
            1 if print_job.released_by_operator else 0,
            (
                1 if print_job.validation_passed
                else 0 if print_job.validation_passed is False
                else None
            ),
            json.dumps(print_job.validation_errors),
        ),
    )
    created_id = int(cursor.lastrowid)
    if not print_job.screenshot_url:
        connection.execute(
            """
            UPDATE print_jobs
            SET screenshot_url = ?
            WHERE id = ?
            """,
            (f"/api/print-queue/jobs/{created_id}/screenshot", created_id),
        )
    return created_id


def _held_print_job_from_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    job_name: str,
    cutoff_at: datetime,
) -> "PrintJob":
    from ..schemas import PrintJob

    return PrintJob(
        job_name=job_name,
        scene_id=None,
        print_job_id=None,
        status=HOLDING_STATUS,
        preset=_manifest_preset_summary(manifest),
        preset_names=manifest.preset_names,
        compatibility_key=manifest.compatibility_key,
        case_ids=_manifest_case_ids_by_file_order(manifest),
        manifest_json=manifest.model_dump(),
        printer_type=manifest.printer_group,
        resin=manifest.material_label,
        layer_height_microns=(
            int(manifest.layer_thickness_mm * 1000)
            if manifest.layer_thickness_mm is not None
            else None
        ),
        estimated_density=manifest.estimated_density,
        density_target=settings.print_hold_density_target,
        hold_cutoff_at=cutoff_at.isoformat(),
        hold_reason="below_density_target",
        validation_passed=None,
        validation_errors=[],
    )


def _load_held_replan_rows(settings: "Settings") -> tuple[list[int], list["ClassificationRow"]]:
    from contextlib import closing

    from ..database import _load_rows_by_ids, connect, list_print_jobs

    held_job_ids: list[int] = []
    held_row_ids: list[int] = []
    for job in list_print_jobs(settings):
        if job.status != HOLDING_STATUS or job.id is None or job.manifest_json is None:
            continue
        held_job_ids.append(job.id)
        for group in job.manifest_json.get("import_groups", []):
            if not isinstance(group, dict):
                continue
            for file_spec in group.get("files", []):
                if isinstance(file_spec, dict) and file_spec.get("row_id") is not None:
                    held_row_ids.append(int(file_spec["row_id"]))

    if not held_row_ids:
        return held_job_ids, []

    with closing(connect(settings)) as connection:
        held_rows = _load_rows_by_ids(connection, sorted(set(held_row_ids)))

    return held_job_ids, [
        row.model_copy(update={"status": "Ready"})
        for row in held_rows
        if row.row_id is not None
    ]


def release_due_held_jobs(settings: "Settings") -> None:
    """Release held builds that crossed cutoff during this process lifetime."""
    from datetime import datetime

    from ..database import list_print_jobs

    if not _held_job_ids_created_this_process:
        return

    now = _now()
    for job in list_print_jobs(settings):
        if job.id not in _held_job_ids_created_this_process:
            continue
        if job.status != HOLDING_STATUS or not job.hold_cutoff_at:
            _held_job_ids_created_this_process.discard(job.id)
            continue
        try:
            cutoff_at = datetime.fromisoformat(job.hold_cutoff_at)
        except ValueError:
            continue
        if now < cutoff_at:
            continue
        try:
            release_held_print_job(settings, job.id, released_by_operator=False)
        except Exception:
            continue
        _held_job_ids_created_this_process.discard(job.id)


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

    assert_preform_ready(settings)

    rows = []
    for row_id in row_ids:
        row = get_upload_row_by_id(settings, row_id)
        if row:
            rows.append(row)

    ready_rows = [r for r in rows if r.status == "Ready"]
    if not ready_rows:
        return rows

    held_job_ids, held_replan_rows = _load_held_replan_rows(settings)
    planning_rows = held_replan_rows + [
        row for row in ready_rows if row.row_id not in {
            held_row.row_id for held_row in held_replan_rows
        }
    ]

    manifests = plan_build_manifests(planning_rows)
    if not manifests:
        return rows

    now = _now_iso()
    hold_now = _now()
    cutoff_at = _parse_cutoff_today(settings.print_hold_cutoff_local_time, hold_now)
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    rows_by_id = {
        row.row_id: row
        for row in planning_rows
        if row.row_id is not None
    }
    for row in planning_rows:
        if row.case_id:
            rows_by_case.setdefault(row.case_id, []).append(row)
    final_index_by_compatibility: dict[str | None, int] = {}
    for index, manifest in enumerate(manifests):
        if manifest.planning_status == "planned":
            final_index_by_compatibility[manifest.compatibility_key] = index

    with closing(connect(settings)) as connection:
        try:
            if held_job_ids:
                connection.execute(
                    f"""
                    DELETE FROM print_jobs
                    WHERE id IN ({",".join("?" for _ in held_job_ids)})
                    """,
                    tuple(held_job_ids),
                )
                for held_job_id in held_job_ids:
                    _held_job_ids_created_this_process.discard(held_job_id)

            for manifest_index, manifest in enumerate(manifests):
                manifest_rows = [
                    row
                    for case_id in manifest.case_ids
                    for row in rows_by_case.get(case_id, [])
                ]
                if not manifest_rows:
                    continue

                for row in manifest_rows:
                    connection.execute(
                        """
                        UPDATE upload_rows
                        SET queue_section = 'in_progress',
                            handoff_stage = 'Processing',
                            current_event_at = ?
                        WHERE id = ?
                        """,
                        (now, row.row_id),
                    )
                    metadata = json.dumps({
                        "status": row.status,
                        "handoff_stage": "Processing",
                        "queue_section": "in_progress",
                    })
                    connection.execute(
                        """
                        INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (row.row_id, "handoff_started", now, metadata),
                    )

                if manifest.planning_status != "planned" or not manifest.import_groups:
                    review_reason = (
                        f"Build planning requires manual review: {manifest.non_plannable_reason}"
                    )
                    for row in manifest_rows:
                        connection.execute(
                            """
                            UPDATE upload_rows
                            SET status = 'Needs Review',
                                queue_section = 'analysis',
                                handoff_stage = NULL,
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

                if _should_hold_manifest(
                    settings,
                    manifest,
                    manifest_index,
                    final_index_by_compatibility,
                    hold_now,
                ):
                    job_name = _generate_unique_job_name_for_manifest(
                        connection,
                        datetime.now(),
                        manifest,
                    )
                    held_job = _held_print_job_from_manifest(
                        settings,
                        manifest,
                        job_name,
                        cutoff_at,
                    )
                    created_print_job_id = _insert_print_job(connection, held_job, now)
                    _held_job_ids_created_this_process.add(created_print_job_id)
                    for row in manifest_rows:
                        connection.execute(
                            """
                            UPDATE upload_rows
                            SET status = 'Submitted',
                                queue_section = 'in_progress',
                                handoff_stage = ?,
                                linked_job_name = ?,
                                linked_print_job_id = ?,
                                current_event_at = ?
                            WHERE id = ?
                            """,
                            (
                                HOLDING_STATUS,
                                job_name,
                                created_print_job_id,
                                now,
                                row.row_id,
                            ),
                        )
                        metadata = json.dumps({
                            "status": "Submitted",
                            "queue_section": "in_progress",
                            "handoff_stage": HOLDING_STATUS,
                            "job_name": job_name,
                            "linked_print_job_id": created_print_job_id,
                            "manifest": manifest.model_dump(),
                            "estimated_density": manifest.estimated_density,
                            "density_target": settings.print_hold_density_target,
                        })
                        connection.execute(
                            """
                            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (row.row_id, "build_holding", now, metadata),
                        )
                    continue

                active_manifest = manifest
                while True:
                    active_rows = _manifest_rows(active_manifest, rows_by_id)
                    job_name = _generate_unique_job_name_for_manifest(
                        connection,
                        datetime.now(),
                        active_manifest,
                    )
                    result = process_print_manifest(
                        settings,
                        active_manifest,
                        active_rows,
                        batch_number=1,
                        job_name=job_name,
                    )
                    active_case_ids = _manifest_case_ids_by_file_order(active_manifest)
                    if not result.get("review_required", False) or len(active_case_ids) == 1:
                        break

                    rollback_case_id = _last_added_case_id(active_manifest)
                    if rollback_case_id is None:
                        break

                    retry_case_ids = [
                        case_id
                        for case_id in active_case_ids
                        if case_id != rollback_case_id
                    ]
                    if not retry_case_ids:
                        break
                    active_manifest = _subset_manifest(active_manifest, retry_case_ids)

                accepted_manifest = result["manifest"]
                accepted_rows = _manifest_rows(accepted_manifest, rows_by_id)
                accepted_row_ids = {row.row_id for row in accepted_rows if row.row_id is not None}
                deferred_rows = [
                    row
                    for row in manifest_rows
                    if row.row_id is not None and row.row_id not in accepted_row_ids
                ]

                for row in deferred_rows:
                    connection.execute(
                        """
                        UPDATE upload_rows
                        SET queue_section = 'analysis',
                            handoff_stage = NULL,
                            current_event_at = ?
                        WHERE id = ?
                        """,
                        (now, row.row_id),
                    )
                    metadata = json.dumps({
                        "status": row.status,
                        "handoff_stage": None,
                        "queue_section": "analysis",
                    })
                    connection.execute(
                        """
                        INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (row.row_id, "handoff_deferred", now, metadata),
                    )

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
                                queue_section = 'analysis',
                                handoff_stage = NULL,
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
                    form_file_path=result.get("form_file_path"),
                    screenshot_url=result.get("screenshot_url"),
                    status=result.get("status", "Queued"),
                    preset=result["preset"],
                    preset_names=result.get("preset_names", []),
                    compatibility_key=result.get("compatibility_key"),
                    case_ids=result["case_ids"],
                    manifest_json=result.get("manifest_json"),
                    printer_type=result.get("printer_type"),
                    resin=result.get("resin"),
                    layer_height_microns=result.get("layer_height_microns"),
                    estimated_density=result.get("estimated_density"),
                    density_target=settings.print_hold_density_target,
                    validation_passed=result.get("validation_passed"),
                    validation_errors=result.get("validation_errors", []),
                )

                created_print_job_id = _insert_print_job(connection, print_job, now)

                for row in accepted_rows:
                    connection.execute(
                        """
                        UPDATE upload_rows
                        SET status = 'Submitted',
                            queue_section = 'history',
                            handoff_stage = 'Queued',
                            linked_job_name = ?,
                            linked_print_job_id = ?,
                            current_event_at = ?
                        WHERE id = ?
                        """,
                        (
                            result["job_name"],
                            created_print_job_id,
                            now,
                            row.row_id,
                        ),
                    )
                    metadata = json.dumps({
                        "status": "Submitted",
                        "queue_section": "history",
                        "handoff_stage": "Queued",
                        "job_name": result["job_name"],
                        "linked_print_job_id": created_print_job_id,
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


def release_held_print_job(
    settings: "Settings",
    job_id: int,
    *,
    released_by_operator: bool = True,
) -> "PrintJob":
    """Release a held build through the normal PreForm handoff path."""
    from contextlib import closing

    from ..database import _load_rows_by_ids, _now_iso, connect, get_print_job_by_id
    from ..schemas import BuildManifest

    assert_preform_ready(settings)
    job = get_print_job_by_id(settings, job_id)
    if job is None:
        raise LookupError("Job not found")
    if job.status != HOLDING_STATUS:
        raise ValueError("Only held jobs can be released.")
    if job.manifest_json is None:
        raise ValueError("Held job is missing its build manifest.")

    manifest = BuildManifest.model_validate(job.manifest_json)
    row_ids = [
        file_spec.row_id
        for group in manifest.import_groups
        for file_spec in group.files
    ]
    now = _now_iso()

    with closing(connect(settings)) as connection:
        rows = _load_rows_by_ids(connection, row_ids)
        result = process_print_manifest(
            settings,
            manifest,
            rows,
            batch_number=1,
            job_name=job.job_name,
        )
        accepted_rows = _manifest_rows(result["manifest"], {
            row.row_id: row for row in rows if row.row_id is not None
        })
        accepted_row_ids = [row.row_id for row in accepted_rows if row.row_id is not None]

        if result.get("review_required"):
            review_reason = (
                "PreForm validation requires manual review: "
                f"{result.get('error_message') or 'scene_validation_failed'}"
            )
            for row_id in accepted_row_ids:
                connection.execute(
                    """
                    UPDATE upload_rows
                    SET status = 'Needs Review',
                        queue_section = 'analysis',
                        handoff_stage = NULL,
                        review_required = 1,
                        review_reason = ?,
                        current_event_at = ?
                    WHERE id = ?
                    """,
                    (review_reason, now, row_id),
                )
            connection.execute(
                """
                UPDATE print_jobs
                SET status = 'Failed',
                    scene_id = ?,
                    form_file_path = ?,
                    error_message = ?,
                    release_reason = ?,
                    released_by_operator = ?,
                    validation_passed = 0,
                    validation_errors_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    result.get("scene_id"),
                    result.get("form_file_path"),
                    result.get("error_message"),
                    "operator_release" if released_by_operator else "cutoff_release",
                    1 if released_by_operator else 0,
                    json.dumps(result.get("validation_errors", [])),
                    now,
                    job_id,
                ),
            )
        else:
            for row_id in accepted_row_ids:
                connection.execute(
                    """
                    UPDATE upload_rows
                    SET status = 'Submitted',
                        queue_section = 'history',
                        handoff_stage = 'Queued',
                        linked_job_name = ?,
                        linked_print_job_id = ?,
                        current_event_at = ?
                    WHERE id = ?
                    """,
                    (job.job_name, job_id, now, row_id),
                )
            connection.execute(
                """
                UPDATE print_jobs
                SET scene_id = ?,
                    print_job_id = ?,
                    form_file_path = ?,
                    screenshot_url = ?,
                    status = ?,
                    preset = ?,
                    preset_names_json = ?,
                    compatibility_key = ?,
                    case_ids = ?,
                    manifest_json = ?,
                    printer_type = ?,
                    resin = ?,
                    layer_height_microns = ?,
                    estimated_density = ?,
                    density_target = ?,
                    release_reason = ?,
                    released_by_operator = ?,
                    validation_passed = ?,
                    validation_errors_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    result["scene_id"],
                    result["print_job_id"],
                    result.get("form_file_path"),
                    result.get("screenshot_url"),
                    result.get("status", "Queued"),
                    result["preset"],
                    json.dumps(result.get("preset_names", [])),
                    result.get("compatibility_key"),
                    json.dumps(result["case_ids"]),
                    json.dumps(result.get("manifest_json")),
                    result.get("printer_type"),
                    result.get("resin"),
                    result.get("layer_height_microns"),
                    result.get("estimated_density"),
                    settings.print_hold_density_target,
                    "operator_release" if released_by_operator else "cutoff_release",
                    1 if released_by_operator else 0,
                    1 if result.get("validation_passed") else 0,
                    json.dumps(result.get("validation_errors", [])),
                    now,
                    job_id,
                ),
            )

        connection.commit()
        refreshed = connection.execute(
            "SELECT id FROM print_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if refreshed is None:
            raise RuntimeError("Released job could not be reloaded.")

    released_job = get_print_job_by_id(settings, job_id)
    if released_job is None:
        raise RuntimeError("Released job could not be reloaded.")
    return released_job
