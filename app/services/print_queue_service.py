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
import math
import os
import re
import shutil
import sqlite3
import struct
import zlib
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from time import perf_counter
from typing import TYPE_CHECKING, Any, Iterable
from uuid import uuid4

from .formlabs_web_client import FormlabsWebClient
from .preset_catalog import SUPPORTED_PRINTER_GROUPS, get_preset_profile
from core.stl_validator import validate_stl_file

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
    tray_left = 70
    tray_top = 42
    tray_width = 820
    tray_height = 410
    _draw_rect(
        pixels,
        width,
        height,
        left=tray_left,
        top=tray_top,
        rect_width=tray_width,
        rect_height=tray_height,
        color=(214, 225, 236),
    )
    _draw_rect(
        pixels,
        width,
        height,
        left=tray_left + 12,
        top=tray_top + 12,
        rect_width=tray_width - 24,
        rect_height=tray_height - 24,
        color=(242, 247, 252),
    )

    files = []
    manifest = job.manifest_json or {}
    for group in manifest.get("import_groups", []) if isinstance(manifest, dict) else []:
        if isinstance(group, dict):
            files.extend(file for file in group.get("files", []) if isinstance(file, dict))

    if not files:
        files = [{"xy_footprint_estimate": 2500.0}]

    density = job.estimated_density
    if density is None and isinstance(manifest, dict):
        density = manifest.get("estimated_density")
    try:
        density_value = max(0.0, float(density or 0.0))
    except (TypeError, ValueError):
        density_value = 0.0
    try:
        density_target = max(0.01, float(job.density_target or 0.40))
    except (TypeError, ValueError):
        density_target = 0.40
    density_ratio = max(0.0, min(1.0, density_value / density_target))
    gauge_width = tray_width - 120
    gauge_left = tray_left + 60
    gauge_top = tray_top + tray_height + 22
    _draw_rect(
        pixels,
        width,
        height,
        left=gauge_left,
        top=gauge_top,
        rect_width=gauge_width,
        rect_height=18,
        color=(219, 226, 234),
    )
    _draw_rect(
        pixels,
        width,
        height,
        left=gauge_left,
        top=gauge_top,
        rect_width=max(4, int(gauge_width * density_ratio)),
        rect_height=18,
        color=(58, 132, 196) if density_value < density_target else (66, 153, 112),
    )

    max_area = max(
        float(file.get("xy_footprint_estimate") or 1200.0)
        for file in files
    )
    model_count = max(1, len(files))
    column_count = max(1, math.ceil(math.sqrt(model_count * (tray_width / tray_height))))
    row_count = max(1, math.ceil(model_count / column_count))
    cell_width = max(1, (tray_width - 60) // column_count)
    cell_height = max(1, (tray_height - 60) // row_count)
    for index, file in enumerate(files):
        area = float(file.get("xy_footprint_estimate") or 1200.0)
        scale = max(0.25, min(1.0, math.sqrt(area / max_area)))
        model_width = max(12, int(cell_width * 0.72 * scale))
        model_height = max(12, int(cell_height * 0.72 * scale))
        column = index % column_count
        row = index // column_count
        center_x = tray_left + 30 + column * cell_width + cell_width // 2
        center_y = tray_top + 30 + row * cell_height + cell_height // 2
        preset_name = str(file.get("preset_name") or "")
        color = (58, 132, 196)
        highlight = (116, 178, 224)
        if "tooth" in preset_name.lower():
            color = (112, 89, 168)
            highlight = (157, 139, 205)
        _draw_rect(
            pixels,
            width,
            height,
            left=center_x - model_width // 2,
            top=center_y - model_height // 2,
            rect_width=model_width,
            rect_height=model_height,
            color=color,
        )
        _draw_rect(
            pixels,
            width,
            height,
            left=center_x - model_width // 2 + 8,
            top=center_y - model_height // 2 + 8,
            rect_width=max(1, model_width - 16),
            rect_height=max(1, model_height - 16),
            color=highlight,
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
    for key in ("id", "device_id", "printer_id"):
        value = device.get(key)
        if value:
            return str(value)
    return None


def _device_name(device: dict[str, Any]) -> str | None:
    for key in ("name", "display_name", "id", "device_id", "printer_id"):
        value = device.get(key)
        if value:
            return str(value)
    return None


def _device_model(device: dict[str, Any]) -> str | None:
    for key in ("model", "product_name", "type"):
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


class DeviceDispatchValidationError(ValueError):
    def __init__(self, payload: dict[str, object], status_code: int = 422):
        super().__init__("Selected rows cannot be dispatched to the selected printer.")
        self.payload = payload
        self.status_code = status_code


class BuildLaneBusyError(ValueError):
    """Raised when active build prep is already running for a lane."""


def _lane_part(value: object) -> str:
    text = str(value or "unknown").strip() or "unknown"
    return text.replace("|", "/").lower()


def _manifest_layer_height_microns(manifest: "BuildManifest") -> str:
    if manifest.layer_thickness_mm is None:
        return "unknown"
    return str(int(round(float(manifest.layer_thickness_mm) * 1000)))


def _build_lane_key_from_manifest(
    manifest: "BuildManifest",
    *,
    device_id: str | None = None,
) -> str:
    target = f"device:{device_id}" if device_id else f"group:{manifest.printer_group or 'unknown'}"
    return "|".join(
        [
            _lane_part(target),
            _lane_part(manifest.printer_group),
            _lane_part(manifest.material_code),
            _lane_part(manifest.material_label),
            _manifest_layer_height_microns(manifest),
            _lane_part(manifest.print_setting),
        ]
    )


def _build_lane_keys_from_manifests(
    manifests: list["BuildManifest"],
    *,
    device_id: str | None = None,
) -> list[str]:
    lane_keys = {
        _build_lane_key_from_manifest(manifest, device_id=device_id)
        for manifest in manifests
        if manifest.planning_status == "planned" and manifest.import_groups
    }
    return sorted(lane_keys)


def _coalesce_manifests_by_lane_key(
    manifests: list["BuildManifest"],
    *,
    max_layout_density: float | None = None,
) -> list["BuildManifest"]:
    """Merge planned manifests with the same lane key into a single manifest.

    Non-planned manifests are passed through unchanged so they still reach the
    manual-review branch in the dispatch loop.  Only merges when the combined
    xy footprint fits within the printer_xy_budget; otherwise the originals are
    kept so the dispatch loop can process them individually.
    """
    from collections import defaultdict

    if not manifests:
        return []

    lane_key_to_manifests: dict[str, list["BuildManifest"]] = defaultdict(list)
    coalesced: list["BuildManifest"] = []

    for manifest in manifests:
        if manifest.planning_status != "planned" or not manifest.import_groups:
            coalesced.append(manifest)  # pass through non-plannable manifests unchanged
            continue
        lane_key = _build_lane_key_from_manifest(manifest)
        lane_key_to_manifests[lane_key].append(manifest)

    for lane_manifests in lane_key_to_manifests.values():
        if len(lane_manifests) == 1:
            coalesced.append(lane_manifests[0])
            continue

        # Check merged footprint before coalescing to avoid violating print_max_layout_density.
        # plan_build_manifests split these precisely because one tray can't fit all rows.
        first = lane_manifests[0]
        printer_xy_budget = first.printer_xy_budget or 0.0
        max_merged_xy_budget = printer_xy_budget
        if printer_xy_budget > 0 and max_layout_density is not None and max_layout_density > 0:
            max_merged_xy_budget = min(
                printer_xy_budget,
                printer_xy_budget * max_layout_density,
            )
        merged_used_xy = sum(m.used_xy_budget for m in lane_manifests)
        if max_merged_xy_budget > 0 and merged_used_xy > max_merged_xy_budget:
            # Merged footprint exceeds tray capacity — keep originals for individual dispatch.
            coalesced.extend(lane_manifests)
            continue

        merged_groups: list["BuildManifestImportGroup"] = []
        merged_case_ids: list[str] = []
        for manifest in lane_manifests:
            merged_groups.extend(manifest.import_groups)
            merged_case_ids.extend(manifest.case_ids)

        coalesced_manifest = first.model_copy(deep=True)
        coalesced_manifest.import_groups = merged_groups
        coalesced_manifest.case_ids = merged_case_ids
        coalesced_manifest.used_xy_budget = merged_used_xy
        coalesced_manifest.estimated_density = (
            merged_used_xy / printer_xy_budget if printer_xy_budget else 0.0
        )
        coalesced.append(coalesced_manifest)

    return coalesced


@contextmanager
def _build_lane_locks(
    settings: "Settings",
    lane_keys: list[str],
    *,
    operation: str,
):
    from ..database import release_build_lane_lock, try_acquire_build_lane_lock

    owner_token = uuid4().hex
    acquired: list[str] = []
    try:
        for lane_key in sorted(set(lane_keys)):
            if try_acquire_build_lane_lock(settings, lane_key, owner_token, operation):
                acquired.append(lane_key)
                continue
            raise BuildLaneBusyError(
                "Build preparation is already in progress for this printer/material/layer lane. "
                "Wait for the current build to finish or hold, then try again."
            )
        yield
    finally:
        for lane_key in reversed(acquired):
            release_build_lane_lock(settings, lane_key, owner_token)


class PreFormImportFailureError(RuntimeError):
    def __init__(self, failed_case_errors: dict[str, str]):
        super().__init__("No valid cases could be imported by PreFormServer.")
        self.failed_case_errors = failed_case_errors


class PreFormAutoLayoutFailureError(RuntimeError):
    """Raised when PreForm cannot fit the imported models in the work area."""


def _is_auto_layout_fit_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "auto-layout" in message
        and (
            "unable to fit" in message
            or "work area" in message
            or "operation_failed" in message
        )
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
    device_id: str | None = None,
    force_dispatch: bool = False,
) -> str | None:
    mode = getattr(settings, "print_dispatch_mode", "save_form")
    if force_dispatch:
        if not device_id:
            raise RuntimeError("Explicit printer dispatch requires a device id.")
        resolved_device_id = (
            _resolve_virtual_device_id(client)
            if device_id == "__virtual__"
            else device_id
        )
    elif mode == "save_form":
        return None
    elif mode == "virtual":
        resolved_device_id = _resolve_virtual_device_id(client, _resolve_device_id(rows, manifest))
    elif mode == "real":
        resolved_device_id = _resolve_device_id(rows, manifest)
    else:
        raise RuntimeError(f"Unsupported print dispatch mode: {mode}")

    response = client.send_to_printer(scene_id, resolved_device_id, job_name)
    if not isinstance(response, dict):
        raise RuntimeError("PreFormServer returned an invalid print response.")
    return _print_id_from_response(response)


def _dispatch_prepared_scene_if_enabled(
    settings: "Settings",
    result: dict[str, object],
    rows: list["ClassificationRow"],
    *,
    device_id: str | None = None,
) -> str | None:
    from .preform_client import PreFormClient

    scene_id = result.get("scene_id")
    manifest = result.get("manifest")
    job_name = result.get("job_name")
    if not scene_id or manifest is None or not job_name:
        raise RuntimeError("Prepared PreForm scene cannot be dispatched without scene, manifest, and job name.")

    client = PreFormClient(settings.preform_server_url)
    try:
        return _dispatch_scene_if_enabled(
            client=client,
            settings=settings,
            scene_id=str(scene_id),
            manifest=manifest,
            rows=rows,
            job_name=str(job_name),
            device_id=device_id,
            force_dispatch=device_id is not None,
        )
    finally:
        client.close()


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


def _manifest_used_xy_budget(manifest: "BuildManifest") -> float:
    return sum(
        float(file_spec.xy_footprint_estimate or 0.0)
        for group in manifest.import_groups
        for file_spec in group.files
    )


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

    updated_manifest = manifest.model_copy(
        update={
            "case_ids": case_ids,
            "preset_names": sorted(set(preset_names)),
            "import_groups": import_groups,
        }
    )
    used_xy_budget = _manifest_used_xy_budget(updated_manifest)
    printer_xy_budget = float(updated_manifest.printer_xy_budget or 0.0)
    estimated_density = used_xy_budget / printer_xy_budget if printer_xy_budget else 0.0
    return updated_manifest.model_copy(
        update={
            "used_xy_budget": used_xy_budget,
            "estimated_density": estimated_density,
        }
    )


def _move_rows_back_to_analysis(
    connection,
    rows: list["ClassificationRow"],
    *,
    now: str,
    event_type: str,
) -> None:
    for row in rows:
        if row.row_id is None:
            continue
        connection.execute(
            """
            UPDATE upload_rows
            SET status = 'Ready',
                queue_section = 'analysis',
                handoff_stage = NULL,
                linked_job_name = NULL,
                linked_print_job_id = NULL,
                current_event_at = ?
            WHERE id = ?
            """,
            (now, row.row_id),
        )
        connection.execute(
            """
            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                row.row_id,
                event_type,
                now,
                json.dumps({
                    "status": "Ready",
                    "queue_section": "analysis",
                    "handoff_stage": None,
                }),
            ),
        )


def _mark_rows_waiting_for_repack(
    connection,
    rows: list["ClassificationRow"],
    *,
    now: str,
) -> None:
    for row in rows:
        if row.row_id is None:
            continue
        connection.execute(
            """
            UPDATE upload_rows
            SET status = 'Submitted',
                queue_section = 'in_progress',
                handoff_stage = 'Repacking',
                linked_job_name = NULL,
                linked_print_job_id = NULL,
                current_event_at = ?
            WHERE id = ?
            """,
            (now, row.row_id),
        )
        connection.execute(
            """
            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                row.row_id,
                "handoff_repack_pending",
                now,
                json.dumps({
                    "status": "Submitted",
                    "queue_section": "in_progress",
                    "handoff_stage": "Repacking",
                }),
            ),
        )


def _smallest_case_id(manifest: "BuildManifest") -> str | None:
    areas_by_case: dict[str, float] = {}
    first_order_by_case: dict[str, int] = {}
    for group in manifest.import_groups:
        for file_spec in group.files:
            areas_by_case[file_spec.case_id] = (
                areas_by_case.get(file_spec.case_id, 0.0)
                + float(file_spec.xy_footprint_estimate or 0.0)
            )
            first_order_by_case[file_spec.case_id] = min(
                first_order_by_case.get(file_spec.case_id, file_spec.order),
                file_spec.order,
            )
    if not areas_by_case:
        return None
    return min(
        areas_by_case,
        key=lambda case_id: (
            areas_by_case[case_id],
            first_order_by_case.get(case_id, 0),
            case_id,
        ),
    )


def _shrink_manifest_after_layout_failure(
    connection,
    manifest: "BuildManifest",
    row_lookup: dict[int, "ClassificationRow"],
    *,
    now: str,
) -> tuple["BuildManifest", list["ClassificationRow"]] | None:
    active_case_ids = _manifest_case_ids_by_file_order(manifest)
    if len(active_case_ids) <= 1:
        return None

    overflow_case_id = _smallest_case_id(manifest)
    if overflow_case_id is None:
        return None

    retry_case_ids = [
        case_id
        for case_id in active_case_ids
        if case_id != overflow_case_id
    ]
    if not retry_case_ids:
        return None

    deferred_manifest = _subset_manifest(manifest, [overflow_case_id])
    deferred_rows = _manifest_rows(deferred_manifest, row_lookup)
    _mark_rows_waiting_for_repack(
        connection,
        deferred_rows,
        now=now,
    )
    return _subset_manifest(manifest, retry_case_ids), deferred_rows


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
    device_id: str | None = None,
    printer_device_name: str | None = None,
    dispatch_scene: bool = True,
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
        failed_case_errors: dict[str, str] = {}

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
                    error_text = f"{stl_path.name} - {exc}"
                    failed_case_errors[case_id] = error_text
                    logging.error("Failed to import %s (case: %s): %s", stl_path, case_id, exc)
                    case_failed = True
                    break

            if case_failed:
                failed_cases.add(case_id)
                logging.error("Case %s blocked due to import failure", case_id)
            else:
                imported_any = True

        if not imported_any:
            raise PreFormImportFailureError(failed_case_errors)
        if failed_cases:
            active_case_ids = [
                case_id
                for case_id in active_case_ids
                if case_id not in failed_cases
            ]
            manifest = _subset_manifest(manifest, active_case_ids)
            active_rows = _manifest_rows(manifest, row_lookup)

        try:
            client.auto_layout(scene_id)
        except Exception as exc:
            if _is_auto_layout_fit_failure(exc):
                raise PreFormAutoLayoutFailureError(str(exc)) from exc
            raise
        if support_model_ids:
            client.auto_support(scene_id, models=support_model_ids)
            try:
                client.auto_layout(scene_id)
            except Exception as exc:
                if _is_auto_layout_fit_failure(exc):
                    raise PreFormAutoLayoutFailureError(str(exc)) from exc
                raise
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
        print_job_id = (
            _dispatch_scene_if_enabled(
                client=client,
                settings=settings,
                scene_id=scene_id,
                manifest=manifest,
                rows=active_rows,
                job_name=job_name,
                device_id=device_id,
                force_dispatch=device_id is not None,
            )
            if dispatch_scene
            else None
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
            "failed_case_errors": failed_case_errors,
            "manifest": manifest,
            "manifest_json": manifest.model_dump(),
            "status": "Queued",
            "row_count": len(active_rows),
            "review_required": False,
            "validation_passed": bool(validation_result.get("valid", False)),
            "validation_errors": validation_errors,
            "printer_type": manifest.printer_group,
            "printer_device_id": device_id,
            "printer_device_name": printer_device_name,
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


def _should_hold_accepted_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    now: datetime,
) -> bool:
    density_target = getattr(settings, "print_hold_density_target", 0.40)
    if density_target <= 0:
        return False
    if manifest.planning_status != "planned" or not manifest.import_groups:
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
            printer_device_id,
            printer_device_name,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            print_job.printer_device_id,
            print_job.printer_device_name,
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


def _reserved_print_job_from_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    job_name: str,
    *,
    device_id: str | None = None,
    printer_device_name: str | None = None,
) -> "PrintJob":
    from ..schemas import PrintJob

    return PrintJob(
        job_name=job_name,
        scene_id=None,
        print_job_id=None,
        status="Queued",
        preset=_manifest_preset_summary(manifest),
        preset_names=manifest.preset_names,
        compatibility_key=manifest.compatibility_key,
        case_ids=_manifest_case_ids_by_file_order(manifest),
        manifest_json=manifest.model_dump(),
        printer_type=manifest.printer_group,
        printer_device_id=device_id,
        printer_device_name=printer_device_name,
        resin=manifest.material_label,
        layer_height_microns=(
            int(manifest.layer_thickness_mm * 1000)
            if manifest.layer_thickness_mm is not None
            else None
        ),
        estimated_density=manifest.estimated_density,
        density_target=settings.print_hold_density_target,
        validation_passed=None,
        validation_errors=[],
    )


def _reserve_print_job_for_rows(
    connection,
    *,
    settings: "Settings",
    manifest: "BuildManifest",
    rows: list["ClassificationRow"],
    job_name: str,
    now: str,
    device_id: str | None = None,
    printer_device_name: str | None = None,
) -> int:
    reserved_job = _reserved_print_job_from_manifest(
        settings,
        manifest,
        job_name,
        device_id=device_id,
        printer_device_name=printer_device_name,
    )
    created_print_job_id = _insert_print_job(connection, reserved_job, now)
    for row in rows:
        if row.row_id is None:
            continue
        connection.execute(
            """
            UPDATE upload_rows
            SET status = 'Submitted',
                queue_section = 'in_progress',
                handoff_stage = 'Processing',
                linked_job_name = ?,
                linked_print_job_id = ?,
                current_event_at = ?
            WHERE id = ?
            """,
            (job_name, created_print_job_id, now, row.row_id),
        )
        metadata = json.dumps({
            "status": "Submitted",
            "queue_section": "in_progress",
            "handoff_stage": "Processing",
            "job_name": job_name,
            "linked_print_job_id": created_print_job_id,
        })
        connection.execute(
            """
            INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (row.row_id, "handoff_started", now, metadata),
        )
    return created_print_job_id


def _update_reserved_print_job_from_result(
    connection,
    *,
    job_id: int,
    result: dict[str, object],
    settings: "Settings",
    now: str,
) -> None:
    screenshot_url = result.get("screenshot_url") or f"/api/print-queue/jobs/{job_id}/screenshot"
    connection.execute(
        """
        UPDATE print_jobs
        SET scene_id = ?,
            print_job_id = ?,
            status = ?,
            preset = ?,
            preset_names_json = ?,
            compatibility_key = ?,
            case_ids = ?,
            manifest_json = ?,
            updated_at = ?,
            screenshot_url = ?,
            form_file_path = ?,
            printer_type = ?,
            printer_device_id = ?,
            printer_device_name = ?,
            resin = ?,
            layer_height_microns = ?,
            estimated_density = ?,
            density_target = ?,
            validation_passed = ?,
            validation_errors_json = ?
        WHERE id = ?
        """,
        (
            result.get("scene_id"),
            result.get("print_job_id"),
            result.get("status", "Queued"),
            result["preset"],
            json.dumps(result.get("preset_names", [])),
            result.get("compatibility_key"),
            json.dumps(result["case_ids"]),
            json.dumps(result.get("manifest_json")) if result.get("manifest_json") is not None else None,
            now,
            screenshot_url,
            result.get("form_file_path"),
            result.get("printer_type"),
            result.get("printer_device_id"),
            result.get("printer_device_name"),
            result.get("resin"),
            result.get("layer_height_microns"),
            result.get("estimated_density"),
            settings.print_hold_density_target,
            (
                1 if result.get("validation_passed")
                else 0 if result.get("validation_passed") is False
                else None
            ),
            json.dumps(result.get("validation_errors", [])),
            job_id,
        ),
    )
    _screenshot_cache.pop(job_id, None)


def _update_reserved_print_job_as_held(
    connection,
    *,
    job_id: int,
    result: dict[str, object],
    settings: "Settings",
    cutoff_at: datetime,
    now: str,
    hold_reason: str = "below_density_target",
) -> None:
    screenshot_url = result.get("screenshot_url") or f"/api/print-queue/jobs/{job_id}/screenshot"
    connection.execute(
        """
        UPDATE print_jobs
        SET scene_id = ?,
            print_job_id = NULL,
            status = ?,
            preset = ?,
            preset_names_json = ?,
            compatibility_key = ?,
            case_ids = ?,
            manifest_json = ?,
            updated_at = ?,
            screenshot_url = ?,
            form_file_path = ?,
            printer_type = ?,
            printer_device_id = ?,
            printer_device_name = ?,
            resin = ?,
            layer_height_microns = ?,
            estimated_density = ?,
            density_target = ?,
            hold_cutoff_at = ?,
            hold_reason = ?,
            release_reason = NULL,
            released_by_operator = 0,
            validation_passed = ?,
            validation_errors_json = ?
        WHERE id = ?
        """,
        (
            result.get("scene_id"),
            HOLDING_STATUS,
            result["preset"],
            json.dumps(result.get("preset_names", [])),
            result.get("compatibility_key"),
            json.dumps(result["case_ids"]),
            json.dumps(result.get("manifest_json")) if result.get("manifest_json") is not None else None,
            now,
            screenshot_url,
            result.get("form_file_path"),
            result.get("printer_type"),
            result.get("printer_device_id"),
            result.get("printer_device_name"),
            result.get("resin"),
            result.get("layer_height_microns"),
            result.get("estimated_density"),
            settings.print_hold_density_target,
            cutoff_at.isoformat(),
            hold_reason,
            (
                1 if result.get("validation_passed")
                else 0 if result.get("validation_passed") is False
                else None
            ),
            json.dumps(result.get("validation_errors", [])),
            job_id,
        ),
    )
    _screenshot_cache.pop(job_id, None)

    # Remove any stale held job for the same lane that was created by a concurrent
    # dispatch call (e.g. double-click). The job we just updated is the authoritative one.
    lane_compat_key = result.get("compatibility_key")
    device_id_val = result.get("printer_device_id")
    if lane_compat_key is not None:
        connection.execute(
            """
            DELETE FROM print_jobs
            WHERE status = ?
              AND compatibility_key = ?
              AND printer_device_id IS ?
              AND id != ?
            """,
            (HOLDING_STATUS, lane_compat_key, device_id_val, job_id),
        )


def _load_held_replan_rows(
    settings: "Settings",
    *,
    lane_keys: set[str] | None = None,
    device_id: str | None = None,
) -> tuple[list[int], list["ClassificationRow"]]:
    from contextlib import closing

    from ..database import _load_rows_by_ids, connect, list_print_jobs
    from ..schemas import BuildManifest

    held_job_ids: list[int] = []
    held_row_ids: list[int] = []
    for job in list_print_jobs(settings):
        if job.status != HOLDING_STATUS or job.id is None or job.manifest_json is None:
            continue
        try:
            manifest = BuildManifest.model_validate(job.manifest_json)
        except Exception:
            continue
        job_lane_key = _build_lane_key_from_manifest(
            manifest,
            device_id=job.printer_device_id if job.printer_device_id else device_id,
        )
        if lane_keys is not None and job_lane_key not in lane_keys:
            continue
        held_job_ids.append(job.id)
        if job.hold_reason == "busy_lane":
            # busy_lane jobs are lane-scoped stale reservations. Delete matching jobs
            # without merging their rows into density-target replanning.
            continue
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


def _group_result(
    *,
    row_ids: list[int],
    status: str,
    manifest_id: str | None = None,
    job_name: str | None = None,
    print_job_id: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "manifest_id": manifest_id,
        "status": status,
        "row_ids": row_ids,
        "job_name": job_name,
        "print_job_id": print_job_id,
        "error": error,
    }


def _send_to_print_payload(
    *,
    groups: list[dict[str, object]] | None = None,
    quarantined_cases: list[dict[str, object]] | None = None,
    blocked_groups: list[dict[str, object]] | None = None,
    rows: list["ClassificationRow"] | None = None,
    prevalidation_ms: int | None = None,
) -> dict[str, object]:
    return {
        "groups": groups or [],
        "quarantined_cases": quarantined_cases or [],
        "blocked_groups": blocked_groups or [],
        "rows": rows or [],
        "prevalidation_ms": prevalidation_ms,
    }


def _list_devices_for_dispatch(settings: "Settings") -> list[dict[str, Any]]:
    from .preform_client import PreFormClient

    client = PreFormClient(settings.preform_server_url)
    try:
        return _normalize_device_list(client.list_devices())
    finally:
        client.close()


def _selected_dispatch_device(devices: list[dict[str, Any]], device_id: str) -> dict[str, object] | None:
    for device in devices:
        if not isinstance(device, dict):
            continue
        if _device_identifier(device) != device_id:
            continue
        is_virtual = _is_virtual_device(device)
        model = _device_model(device)
        if model not in SUPPORTED_PRINTER_GROUPS:
            raise DeviceDispatchValidationError(
                _send_to_print_payload(
                    blocked_groups=[
                        _group_result(
                            row_ids=[],
                            status="failed",
                            error=(
                                f"Selected printer model {model or 'unknown'} is not supported. "
                                "Choose a Form 4BL or Form 4B printer."
                            ),
                        )
                    ]
                )
            )
        return {
            "device_id": device_id,
            "device_name": _device_name(device),
            "model": model,
            "is_virtual": is_virtual,
        }
    return None


def _case_key(row: "ClassificationRow") -> str:
    if row.case_id:
        return row.case_id
    return f"row-{row.row_id or row.file_name}"


def _prevalidate_dispatch_rows(
    rows: list["ClassificationRow"],
) -> tuple[list["ClassificationRow"], list[dict[str, object]], int]:
    started_at = perf_counter()
    rows_by_case: dict[str, list["ClassificationRow"]] = {}
    failure_by_case: dict[str, str] = {}

    for row in rows:
        rows_by_case.setdefault(_case_key(row), []).append(row)
        if _case_key(row) in failure_by_case:
            continue
        if not row.file_path:
            failure_by_case[_case_key(row)] = f"{row.file_name} - missing STL file path"
            continue
        validation = validate_stl_file(row.file_path)
        if not validation.is_valid:
            failure_by_case[_case_key(row)] = f"{row.file_name} - {validation.message}"

    quarantined_cases = [
        {
            "case_id": None if case_key.startswith("row-") else case_key,
            "row_ids": [
                row.row_id
                for row in case_rows
                if row.row_id is not None
            ],
            "reason": reason,
        }
        for case_key, reason in failure_by_case.items()
        if (case_rows := rows_by_case.get(case_key))
    ]
    valid_rows = [
        row
        for row in rows
        if _case_key(row) not in failure_by_case
    ]
    prevalidation_ms = int((perf_counter() - started_at) * 1000)
    logging.info(
        "Dispatch prevalidation finished in %sms for %s selected rows; quarantined_cases=%s",
        prevalidation_ms,
        len(rows),
        len(quarantined_cases),
    )
    return valid_rows, quarantined_cases, prevalidation_ms


def _mark_cases_needs_review(
    connection,
    cases: list[dict[str, object]],
    *,
    event_type: str,
    now: str,
) -> None:
    for case in cases:
        reason = str(case["reason"])
        row_ids = [row_id for row_id in case.get("row_ids", []) if row_id is not None]
        if not row_ids:
            continue
        placeholders = ",".join("?" for _ in row_ids)
        connection.execute(
            f"""
            UPDATE upload_rows
            SET status = 'Needs Review',
                queue_section = 'analysis',
                handoff_stage = NULL,
                review_required = 1,
                review_reason = ?,
                current_event_at = ?
            WHERE id IN ({placeholders})
            """,
            (reason, now, *row_ids),
        )
        for row_id in row_ids:
            connection.execute(
                """
                INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    row_id,
                    event_type,
                    now,
                    json.dumps({
                        "status": "Needs Review",
                        "reason": reason,
                        "case_id": case.get("case_id"),
                    }),
                ),
            )


def _mark_cases_needs_review_with_retry(
    connection,
    cases: list[dict[str, object]],
    *,
    event_type: str,
    now: str,
    attempts: int = 3,
) -> None:
    if not cases:
        return
    for attempt in range(1, attempts + 1):
        try:
            _mark_cases_needs_review(
                connection,
                cases,
                event_type=event_type,
                now=now,
            )
            return
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == attempts:
                raise
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            sleep(0.25 * attempt)


def _selected_model_rows(
    rows: list["ClassificationRow"],
    device: dict[str, object],
) -> list["ClassificationRow"]:
    if device.get("is_virtual"):
        return rows
    selected_model = device.get("model")
    return [
        row.model_copy(update={"printer": selected_model})
        for row in rows
    ]


def _send_ready_rows_to_device(
    settings: "Settings",
    row_ids: list[int],
    device_id: str,
) -> dict[str, object]:
    from ..database import _load_rows_by_ids, _now_iso, connect, get_upload_row_by_id
    from .build_planning import plan_build_manifests
    from .planning_preview import build_manifest_assignment_id, manifest_row_ids

    if not row_ids:
        return _send_to_print_payload()

    assert_preform_ready(settings)
    rows = [
        row
        for row_id in row_ids
        if (row := get_upload_row_by_id(settings, row_id)) is not None
    ]
    ready_rows = [row for row in rows if row.status == "Ready"]
    if not ready_rows:
        raise DeviceDispatchValidationError(
            _send_to_print_payload(
                blocked_groups=[
                    _group_result(
                        row_ids=row_ids,
                        status="failed",
                        error="No selected rows are Ready for print dispatch.",
                    )
                ],
                rows=rows,
            )
        )

    try:
        devices = _list_devices_for_dispatch(settings)
    except Exception as exc:
        raise DeviceDispatchValidationError(
            _send_to_print_payload(
                blocked_groups=[
                    _group_result(
                        row_ids=[row.row_id for row in ready_rows if row.row_id is not None],
                        status="failed",
                        error=f"PreFormServer cannot provide printer discovery: {exc}",
                    )
                ],
                rows=rows,
            )
        ) from exc

    device = _selected_dispatch_device(devices, device_id)
    if device is None:
        raise DeviceDispatchValidationError(
            _send_to_print_payload(
                blocked_groups=[
                    _group_result(
                        row_ids=[row.row_id for row in ready_rows if row.row_id is not None],
                        status="failed",
                        error=f"Selected printer device {device_id} is no longer available.",
                    )
                ],
                rows=rows,
            )
        )

    prevalidated_rows, quarantined_cases, prevalidation_ms = _prevalidate_dispatch_rows(ready_rows)
    initial_planning_rows = _selected_model_rows(prevalidated_rows, device)
    initial_manifests = plan_build_manifests(
        initial_planning_rows,
        max_layout_density=settings.print_max_layout_density,
    )
    lane_keys = set(
        _build_lane_keys_from_manifests(
            initial_manifests,
            device_id=str(device["device_id"]),
        )
    )
    held_job_ids, held_replan_rows = _load_held_replan_rows(
        settings,
        lane_keys=lane_keys,
        device_id=str(device["device_id"]),
    )
    held_row_ids = {
        row.row_id
        for row in held_replan_rows
        if row.row_id is not None
    }
    groups: list[dict[str, object]] = []
    blocked_groups: list[dict[str, object]] = []
    now = _now_iso()
    with closing(connect(settings)) as connection:
        _mark_cases_needs_review_with_retry(
            connection,
            quarantined_cases,
            event_type="case_quarantined_before_preform",
            now=now,
        )

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

        planning_rows = _selected_model_rows(held_replan_rows, device) + _selected_model_rows(
            [
                row
                for row in prevalidated_rows
                if row.row_id not in held_row_ids
            ],
            device,
        )
        rows_by_id = {
            row.row_id: row
            for row in planning_rows
            if row.row_id is not None
        }

        hold_now = _now()
        cutoff_at = _parse_cutoff_today(settings.print_hold_cutoff_local_time, hold_now)

        # NEW: pack-one-at-a-time pool model
        # live_pool starts as planning_rows; on each iteration plan_build_manifests is
        # called on the current pool to get the densest first tray. On PreForm success,
        # accepted rows are removed from the pool and the next iteration re-plans the
        # remainder. On density-hold or busy-lane, the loop stops (held = final remainder).
        live_pool: list["ClassificationRow"] = list(planning_rows)

        while live_pool:
            ranked_manifests = plan_build_manifests(
                _selected_model_rows(live_pool, device),
                max_layout_density=settings.print_max_layout_density,
            )
            if not ranked_manifests:
                break

            ranked_manifests = _coalesce_manifests_by_lane_key(
                ranked_manifests,
                max_layout_density=settings.print_max_layout_density,
            )

            manifest = ranked_manifests[0]
            manifest_row_id_list = manifest_row_ids(manifest, live_pool)
            manifest_id = build_manifest_assignment_id(manifest, manifest_row_id_list)

            if manifest.planning_status != "planned" or not manifest.import_groups:
                reason = f"Build planning requires manual review: {manifest.non_plannable_reason}"
                blocked_groups.append(
                    _group_result(
                        manifest_id=manifest_id,
                        status="blocked",
                        row_ids=manifest_row_id_list,
                        error=reason,
                    )
                )
                _mark_cases_needs_review_with_retry(
                    connection,
                    [
                        {
                            "case_id": case_id,
                            "row_ids": [
                                row.row_id
                                for row in live_pool
                                if row.row_id is not None and row.case_id == case_id
                            ],
                            "reason": reason,
                        }
                        for case_id in manifest.case_ids
                    ],
                    event_type="manual_review_required",
                    now=now,
                )
                non_plannable_case_ids = set(manifest.case_ids)
                live_pool = [r for r in live_pool if r.case_id not in non_plannable_case_ids]
                continue

            active_manifest = manifest
            active_lane_key = _build_lane_key_from_manifest(
                active_manifest, device_id=str(device["device_id"])
            )
            tray_outcome: str | None = None  # "queued" | "held_busy" | "held_density" | "blocked"

            while True:
                active_rows = _manifest_rows(active_manifest, rows_by_id)
                job_name = _generate_unique_job_name_for_manifest(
                    connection, datetime.now(), active_manifest,
                )
                try:
                    created_print_job_id = _reserve_print_job_for_rows(
                        connection,
                        settings=settings,
                        manifest=active_manifest,
                        rows=active_rows,
                        job_name=job_name,
                        now=now,
                        device_id=str(device["device_id"]),
                        printer_device_name=(
                            str(device["device_name"])
                            if device.get("device_name") is not None
                            else None
                        ),
                    )
                    connection.commit()
                except sqlite3.IntegrityError as exc:
                    connection.rollback()
                    raise DeviceDispatchValidationError(
                        _send_to_print_payload(
                            blocked_groups=[
                                _group_result(
                                    manifest_id=manifest_id,
                                    status="failed",
                                    row_ids=manifest_row_id_list,
                                    error="Selected rows are already being submitted. Refresh the queue and try again.",
                                )
                            ],
                            rows=_load_rows_by_ids(connection, row_ids),
                        )
                    ) from exc

                result = None
                try:
                    with _build_lane_locks(
                        settings, [active_lane_key], operation="send_to_print",
                    ):
                        result = process_print_manifest(
                            settings, active_manifest, active_rows,
                            batch_number=1, job_name=job_name,
                            device_id=str(device["device_id"]),
                            printer_device_name=(
                                str(device["device_name"])
                                if device.get("device_name") is not None
                                else None
                            ),
                            dispatch_scene=False,
                        )
                    break
                except BuildLaneBusyError:
                    busy_message = (
                        "Already preparing a build for this printer/material/layer lane. "
                        "Wait for the current build to finish or hold, then try again."
                    )
                    pool_manifest = active_manifest
                    try:
                        all_pool_planned = plan_build_manifests(
                            _selected_model_rows(live_pool, device),
                            max_layout_density=None,
                        )
                        for candidate in all_pool_planned:
                            if (
                                candidate.planning_status == "planned"
                                and _build_lane_key_from_manifest(
                                    candidate, device_id=str(device["device_id"])
                                ) == active_lane_key
                            ):
                                pool_manifest = candidate
                                break
                    except Exception:
                        pass

                    pool_rows = _manifest_rows(pool_manifest, rows_by_id)
                    hold_result = {
                        "scene_id": None,
                        "preset": _manifest_preset_summary(pool_manifest),
                        "preset_names": pool_manifest.preset_names,
                        "compatibility_key": pool_manifest.compatibility_key,
                        "case_ids": _manifest_case_ids_by_file_order(pool_manifest),
                        "manifest_json": pool_manifest.model_dump(),
                        "form_file_path": None,
                        "printer_type": pool_manifest.printer_group,
                        "printer_device_id": str(device["device_id"]),
                        "printer_device_name": (
                            str(device["device_name"])
                            if device.get("device_name") is not None
                            else None
                        ),
                        "resin": pool_manifest.material_label,
                        "layer_height_microns": (
                            int(pool_manifest.layer_thickness_mm * 1000)
                            if pool_manifest.layer_thickness_mm is not None
                            else None
                        ),
                        "estimated_density": pool_manifest.estimated_density,
                        "validation_passed": None,
                        "validation_errors": [],
                    }
                    _update_reserved_print_job_as_held(
                        connection,
                        job_id=created_print_job_id,
                        result=hold_result,
                        settings=settings,
                        cutoff_at=cutoff_at,
                        now=now,
                        hold_reason="busy_lane",
                    )
                    _held_job_ids_created_this_process.add(created_print_job_id)
                    held_row_ids: list[int] = []
                    for row in pool_rows:
                        if row.row_id is None:
                            continue
                        held_row_ids.append(row.row_id)
                        connection.execute(
                            """UPDATE upload_rows
                               SET status = 'Submitted',
                                   queue_section = 'in_progress',
                                   handoff_stage = ?,
                                   linked_job_name = ?,
                                   linked_print_job_id = ?,
                                   current_event_at = ?
                               WHERE id = ?""",
                            (HOLDING_STATUS, job_name, created_print_job_id, now, row.row_id),
                        )
                        metadata = json.dumps({
                            "status": "Submitted",
                            "queue_section": "in_progress",
                            "handoff_stage": HOLDING_STATUS,
                            "job_name": job_name,
                            "linked_print_job_id": created_print_job_id,
                            "manifest_id": manifest_id,
                            "manifest": pool_manifest.model_dump(),
                            "estimated_density": pool_manifest.estimated_density,
                            "density_target": settings.print_hold_density_target,
                            "error": busy_message,
                        })
                        connection.execute(
                            """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                               VALUES (?, ?, ?, ?)""",
                            (row.row_id, "build_holding", now, metadata),
                        )
                    groups.append(
                        _group_result(
                            manifest_id=manifest_id,
                            status="held",
                            row_ids=held_row_ids,
                            job_name=job_name,
                            error=busy_message,
                        )
                    )
                    tray_outcome = "held_busy"
                    break

                except PreFormAutoLayoutFailureError:
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    shrink_result = _shrink_manifest_after_layout_failure(
                        connection, active_manifest, rows_by_id, now=now,
                    )
                    connection.commit()
                    if shrink_result is None:
                        _move_rows_back_to_analysis(
                            connection, active_rows, now=now, event_type="handoff_failed",
                        )
                        connection.commit()
                        raise
                    shrunken_manifest, deferred_rows = shrink_result
                    active_manifest = shrunken_manifest
                    continue

                except PreFormImportFailureError as exc:
                    failed_case_errors = exc.failed_case_errors
                    if not failed_case_errors:
                        failed_case_errors = {
                            case_id: "no valid cases could be imported"
                            for case_id in active_manifest.case_ids
                        }
                    quarantined_case_ids = set(failed_case_errors.keys())
                    failed_row_ids = [
                        row.row_id
                        for row in live_pool
                        if row.row_id is not None and row.case_id in quarantined_case_ids
                    ]
                    _mark_cases_needs_review_with_retry(
                        connection,
                        [
                            {
                                "case_id": case_id,
                                "row_ids": [
                                    row.row_id
                                    for row in live_pool
                                    if row.row_id is not None and row.case_id == case_id
                                ],
                                "reason": f"PreForm import failed: {error}",
                            }
                            for case_id, error in failed_case_errors.items()
                        ],
                        event_type="case_quarantined_during_preform_import",
                        now=now,
                    )
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    blocked_groups.append(
                        _group_result(
                            manifest_id=manifest_id,
                            status="failed",
                            row_ids=failed_row_ids,
                            error="PreFormServer rejected every STL in this group during import.",
                        )
                    )
                    live_pool = [r for r in live_pool if r.case_id not in quarantined_case_ids]
                    tray_outcome = "blocked"
                    break

                except Exception:
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    _move_rows_back_to_analysis(
                        connection, active_rows, now=now, event_type="handoff_failed",
                    )
                    connection.commit()
                    raise

            if tray_outcome == "held_busy":
                break
            if tray_outcome == "blocked":
                continue

            assert result is not None

            failed_case_errors = result.get("failed_case_errors") or {}
            if isinstance(failed_case_errors, dict) and failed_case_errors:
                _mark_cases_needs_review_with_retry(
                    connection,
                    [
                        {
                            "case_id": case_id,
                            "row_ids": [
                                row.row_id
                                for row in live_pool
                                if row.row_id is not None and row.case_id == case_id
                            ],
                            "reason": f"PreForm import failed: {error}",
                        }
                        for case_id, error in failed_case_errors.items()
                    ],
                    event_type="case_quarantined_during_preform_import",
                    now=now,
                )
                live_pool = [r for r in live_pool if r.case_id not in failed_case_errors.keys()]

            accepted_rows = _manifest_rows(result["manifest"], rows_by_id)
            accepted_row_ids = [r.row_id for r in accepted_rows if r.row_id is not None]
            accepted_manifest = result["manifest"]
            accepted_case_ids = set(accepted_manifest.case_ids)

            if _should_hold_accepted_manifest(settings, accepted_manifest, hold_now):
                _update_reserved_print_job_as_held(
                    connection,
                    job_id=created_print_job_id,
                    result=result,
                    settings=settings,
                    cutoff_at=cutoff_at,
                    now=now,
                )
                _held_job_ids_created_this_process.add(created_print_job_id)
                for row in accepted_rows:
                    if row.row_id is None:
                        continue
                    connection.execute(
                        """UPDATE upload_rows
                           SET status = 'Submitted',
                               queue_section = 'in_progress',
                               handoff_stage = ?,
                               linked_job_name = ?,
                               linked_print_job_id = ?,
                               current_event_at = ?
                           WHERE id = ?""",
                        (HOLDING_STATUS, result["job_name"], created_print_job_id, now, row.row_id),
                    )
                    metadata = json.dumps({
                        "status": "Submitted",
                        "handoff_stage": HOLDING_STATUS,
                        "queue_section": "in_progress",
                        "job_name": result["job_name"],
                        "linked_print_job_id": created_print_job_id,
                        "manifest_id": manifest_id,
                        "manifest": result["manifest_json"],
                        "estimated_density": accepted_manifest.estimated_density,
                        "density_target": settings.print_hold_density_target,
                    })
                    connection.execute(
                        """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                           VALUES (?, ?, ?, ?)""",
                        (row.row_id, "build_holding", now, metadata),
                    )
                groups.append(
                    _group_result(
                        manifest_id=manifest_id,
                        status="held",
                        row_ids=accepted_row_ids,
                        job_name=result["job_name"],
                    )
                )
                break

            try:
                result["print_job_id"] = _dispatch_prepared_scene_if_enabled(
                    settings=settings,
                    result=result,
                    rows=accepted_rows,
                    device_id=str(device["device_id"]),
                )
            except Exception:
                connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                _move_rows_back_to_analysis(
                    connection, accepted_rows, now=now, event_type="handoff_failed",
                )
                connection.commit()
                raise
            _update_reserved_print_job_from_result(
                connection,
                job_id=created_print_job_id,
                result=result,
                settings=settings,
                now=now,
            )
            for row in accepted_rows:
                if row.row_id is None:
                    continue
                connection.execute(
                    """UPDATE upload_rows
                       SET status = 'Submitted',
                           queue_section = 'history',
                           handoff_stage = 'Queued',
                           linked_job_name = ?,
                           linked_print_job_id = ?,
                           current_event_at = ?
                       WHERE id = ?""",
                    (result["job_name"], created_print_job_id, now, row.row_id),
                )
                metadata = json.dumps({
                    "status": "Submitted",
                    "queue_section": "history",
                    "handoff_stage": "Queued",
                    "linked_job_name": result["job_name"],
                    "linked_print_job_id": created_print_job_id,
                    "manifest_id": manifest_id,
                })
                connection.execute(
                    """INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
                       VALUES (?, ?, ?, ?)""",
                    (row.row_id, "submitted_to_print", now, metadata),
                )
            groups.append(
                _group_result(
                    manifest_id=manifest_id,
                    status="submitted",
                    row_ids=accepted_row_ids,
                    job_name=result["job_name"],
                    print_job_id=result.get("print_job_id"),
                )
            )

            live_pool = [r for r in live_pool if r.case_id not in accepted_case_ids]
            connection.commit()

        connection.commit()
        updated_rows = _load_rows_by_ids(connection, row_ids)

    payload = _send_to_print_payload(
        groups=groups,
        quarantined_cases=quarantined_cases,
        blocked_groups=blocked_groups,
        rows=updated_rows,
        prevalidation_ms=prevalidation_ms,
    )
    if not groups:
        status_code = 502 if any(
            "PreFormServer" in str(group.get("error", ""))
            for group in blocked_groups
        ) else 422
        raise DeviceDispatchValidationError(payload, status_code=status_code)
    return payload


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
    device_id: str | None = None,
) -> list["ClassificationRow"] | dict[str, object]:
    """Send Ready rows to print with full PreFormServer handoff."""
    from contextlib import closing

    from ..database import _load_rows_by_ids, _now_iso, connect, get_upload_row_by_id
    from .build_planning import plan_build_manifests

    if device_id:
        return _send_ready_rows_to_device(settings, row_ids, device_id)

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

    initial_manifests = plan_build_manifests(
        ready_rows,
        max_layout_density=settings.print_max_layout_density,
    )
    lane_keys = set(_build_lane_keys_from_manifests(initial_manifests))
    held_job_ids, held_replan_rows = _load_held_replan_rows(settings, lane_keys=lane_keys)
    held_row_ids = {
        held_row.row_id
        for held_row in held_replan_rows
        if held_row.row_id is not None
    }
    planning_rows = held_replan_rows + [
        row for row in ready_rows if row.row_id not in held_row_ids
    ]

    manifests = plan_build_manifests(
        planning_rows,
        max_layout_density=settings.print_max_layout_density,
    )
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

            pending_manifests: list[tuple["BuildManifest", bool]] = [
                (manifest, False) for manifest in manifests
            ]
            retry_rows: list["ClassificationRow"] = []
            while pending_manifests or retry_rows:
                if not pending_manifests and retry_rows:
                    retry_manifests = plan_build_manifests(
                        retry_rows,
                        max_layout_density=settings.print_max_layout_density,
                    )
                    pending_manifests.extend((retry_manifest, True) for retry_manifest in retry_manifests)
                    retry_rows = []
                    continue

                manifest, force_dispatch = pending_manifests.pop(0)
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

                active_manifest = manifest
                created_print_job_id: int | None = None
                while True:
                    active_rows = _manifest_rows(active_manifest, rows_by_id)
                    job_name = _generate_unique_job_name_for_manifest(
                        connection,
                        datetime.now(),
                        active_manifest,
                    )
                    created_print_job_id = _reserve_print_job_for_rows(
                        connection,
                        settings=settings,
                        manifest=active_manifest,
                        rows=active_rows,
                        job_name=job_name,
                        now=now,
                    )
                    connection.commit()
                    try:
                        with _build_lane_locks(
                            settings,
                            [_build_lane_key_from_manifest(active_manifest)],
                            operation="send_to_print",
                        ):
                            result = process_print_manifest(
                                settings,
                                active_manifest,
                                active_rows,
                                batch_number=1,
                                job_name=job_name,
                                dispatch_scene=False,
                            )
                    except PreFormAutoLayoutFailureError:
                        connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                        shrink_result = _shrink_manifest_after_layout_failure(
                            connection,
                            active_manifest,
                            rows_by_id,
                            now=now,
                        )
                        connection.commit()
                        if shrink_result is None:
                            _move_rows_back_to_analysis(
                                connection,
                                active_rows,
                                now=now,
                                event_type="handoff_failed",
                            )
                            connection.commit()
                            raise
                        shrunken_manifest, deferred_retry_rows = shrink_result
                        retry_rows.extend(deferred_retry_rows)
                        active_manifest = shrunken_manifest
                        continue
                    except Exception:
                        connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                        for row in active_rows:
                            connection.execute(
                                """
                                UPDATE upload_rows
                                SET status = 'Ready',
                                    queue_section = 'analysis',
                                    handoff_stage = NULL,
                                    linked_job_name = NULL,
                                    linked_print_job_id = NULL,
                                    current_event_at = ?
                                WHERE id = ?
                                """,
                                (now, row.row_id),
                            )
                        connection.commit()
                        raise
                    active_case_ids = _manifest_case_ids_by_file_order(active_manifest)
                    if not result.get("review_required", False) or len(active_case_ids) == 1:
                        break

                    rollback_case_id = _last_added_case_id(active_manifest)
                    if rollback_case_id is None:
                        break

                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    retry_case_ids = [
                        case_id
                        for case_id in active_case_ids
                        if case_id != rollback_case_id
                    ]
                    if not retry_case_ids:
                        break
                    active_manifest = _subset_manifest(active_manifest, retry_case_ids)

                failed_case_errors = result.get("failed_case_errors") or {}
                if isinstance(failed_case_errors, dict) and failed_case_errors:
                    _mark_cases_needs_review_with_retry(
                        connection,
                        [
                            {
                                "case_id": case_id,
                                "row_ids": [
                                    row.row_id
                                    for row in planning_rows
                                    if row.row_id is not None and row.case_id == case_id
                                ],
                                "reason": f"PreForm import failed: {error}",
                            }
                            for case_id, error in failed_case_errors.items()
                        ],
                        event_type="case_quarantined_during_preform_import",
                        now=now,
                    )

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

                if created_print_job_id is None:
                    raise RuntimeError("Print job reservation was not created.")
                if _should_hold_accepted_manifest(settings, accepted_manifest, hold_now):
                    _update_reserved_print_job_as_held(
                        connection,
                        job_id=created_print_job_id,
                        result=result,
                        settings=settings,
                        cutoff_at=cutoff_at,
                        now=now,
                        hold_reason="below_density_target",
                    )
                    _held_job_ids_created_this_process.add(created_print_job_id)
                    for row in accepted_rows:
                        if row.row_id is None:
                            continue
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
                            (HOLDING_STATUS, result["job_name"], created_print_job_id, now, row.row_id),
                        )
                        metadata = json.dumps({
                            "status": "Submitted",
                            "queue_section": "in_progress",
                            "handoff_stage": HOLDING_STATUS,
                            "job_name": result["job_name"],
                            "linked_print_job_id": created_print_job_id,
                            "manifest": result["manifest_json"],
                            "estimated_density": accepted_manifest.estimated_density,
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

                try:
                    result["print_job_id"] = _dispatch_prepared_scene_if_enabled(
                        settings,
                        result,
                        accepted_rows,
                    )
                except Exception:
                    connection.execute("DELETE FROM print_jobs WHERE id = ?", (created_print_job_id,))
                    _move_rows_back_to_analysis(
                        connection,
                        accepted_rows,
                        now=now,
                        event_type="handoff_failed",
                    )
                    connection.commit()
                    raise

                _update_reserved_print_job_from_result(
                    connection,
                    job_id=created_print_job_id,
                    result=result,
                    settings=settings,
                    now=now,
                )

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
    lane_key = _build_lane_key_from_manifest(
        manifest,
        device_id=job.printer_device_id,
    )
    row_ids = [
        file_spec.row_id
        for group in manifest.import_groups
        for file_spec in group.files
    ]
    now = _now_iso()

    with closing(connect(settings)) as connection:
        rows = _load_rows_by_ids(connection, row_ids)
        with _build_lane_locks(settings, [lane_key], operation="release_held"):
            result = process_print_manifest(
                settings,
                manifest,
                rows,
                batch_number=1,
                job_name=job.job_name,
                device_id=job.printer_device_id,
                printer_device_name=job.printer_device_name,
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
            screenshot_url = result.get("screenshot_url") or f"/api/print-queue/jobs/{job_id}/screenshot"
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
                    screenshot_url,
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
        _screenshot_cache.pop(job_id, None)
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
