from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..schemas import (
    DeviceInfo,
    DispatchModeStatus,
    PreFormDeviceListResponse,
    PreFormPrinterListResponse,
    PreFormPrinterStatus,
    PreFormSetupActionResponse,
    PreFormSetupStatus,
    UpdateDispatchModeRequest,
)
from ..services.preset_catalog import SUPPORTED_PRINTER_GROUPS
from ..services.preform_client import PreFormClient
from ..services.preform_setup_service import (
    PreFormSetupError,
    PreFormSetupService,
    get_preform_setup_status,
)


router = APIRouter(prefix="/api/preform-setup", tags=["preform-setup"])


def _manager(request: Request) -> PreFormSetupService:
    return PreFormSetupService(request.app.state.settings)


def _temp_zip_path(settings, filename: str | None) -> Path:
    safe_name = Path(filename or "preformserver.zip").name or "preformserver.zip"
    temp_dir = settings.data_dir / "preform_setup_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir / f"{uuid4().hex}-{safe_name}"


async def _save_upload(settings, package: UploadFile) -> Path:
    temp_path = _temp_zip_path(settings, package.filename)
    with temp_path.open("wb") as handle:
        shutil.copyfileobj(package.file, handle)
    await package.close()
    return temp_path


def _action_response(status: PreFormSetupStatus, message: str) -> PreFormSetupActionResponse:
    return PreFormSetupActionResponse(status=status, message=message)


def _dispatch_mode_response(request: Request) -> DispatchModeStatus:
    settings = request.app.state.settings
    return DispatchModeStatus(
        mode=settings.print_dispatch_mode,
        default_mode=getattr(
            request.app.state,
            "default_print_dispatch_mode",
            settings.print_dispatch_mode,
        ),
        allowed_modes=["save_form", "virtual"],
    )


def _first_text(device: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = device.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


_MATERIAL_LABEL_CACHE: dict[str, str] | None = None


def _material_label_map(settings) -> dict[str, str]:
    global _MATERIAL_LABEL_CACHE
    if _MATERIAL_LABEL_CACHE is not None:
        return _MATERIAL_LABEL_CACHE
    catalog_path = Path(settings.project_root) / ".omx" / "preform-list-materials-latest.json"
    mapping: dict[str, str] = {}
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        for pt in data.get("printer_types", []):
            for mat in pt.get("materials", []):
                label = mat.get("label", "").strip()
                for ms in mat.get("material_settings", []):
                    code = ms.get("scene_settings", {}).get("material_code", "").strip().upper()
                    if code and label:
                        mapping[code] = label
    except Exception:
        pass
    _MATERIAL_LABEL_CACHE = mapping
    return mapping


def _looks_like_material_code(value: str) -> bool:
    normalized = value.strip().upper()
    return bool(re.fullmatch(r"FL[A-Z0-9]{5,}", normalized))


def _first_readable_material_name(device: dict) -> str | None:
    for key in (
        "material_name",
        "tank_material_name",
        "resin_name",
        "display_material",
        "material_label",
        "material",
        "resin",
    ):
        value = _first_text(device, (key,))
        if value and not _looks_like_material_code(value):
            return value
    return None


def _first_material_code(device: dict) -> str | None:
    for key in (
        "material_code",
        "tank_material_code",
        "resin_code",
        "resin_material_code",
        "material_name",
        "tank_material_name",
        "resin_name",
        "display_material",
        "material_label",
        "material",
        "resin",
    ):
        value = _first_text(device, (key,))
        if value and _looks_like_material_code(value):
            return value
    return None


def _device_identity_text(device: dict) -> str:
    parts = []
    for key in (
        "id",
        "device_id",
        "printer_id",
        "name",
        "model",
        "product_name",
        "type",
        "connection_type",
        "status",
    ):
        value = device.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts).lower()


def _is_virtual_device(device: dict) -> bool:
    for key in ("is_virtual", "virtual", "isVirtual"):
        value = device.get(key)
        if isinstance(value, bool):
            return value
    return "virtual" in _device_identity_text(device)


def _is_setup_center_printer(device: dict) -> bool:
    if _is_virtual_device(device):
        return False
    identity = _device_identity_text(device)
    return "form 4bl" in identity or "form 4b" in identity


def _normalize_device_list(payload) -> list[dict]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        devices = payload.get("devices")
        payload = devices if isinstance(devices, list) else []
    if not isinstance(payload, list):
        return []
    return [device for device in payload if isinstance(device, dict)]


def _normalize_printer(device: dict, settings=None) -> PreFormPrinterStatus:
    device_id = _first_text(device, ("device_id", "id", "printer_id"))
    model = _first_text(device, ("model", "product_name", "type"))
    name = _first_text(device, ("name", "display_name"))
    status = _first_text(device, ("status", "state", "availability"))
    material_name = _first_readable_material_name(device)
    material_code = _first_material_code(device)
    if not material_name and material_code and settings is not None:
        material_name = _material_label_map(settings).get(material_code.upper())
    material = material_name or material_code

    return PreFormPrinterStatus(
        device_id=device_id,
        name=name or device_id or model or "Unnamed printer",
        model=model,
        status=status,
        material=material,
        material_name=material_name,
        material_code=material_code,
        metadata=device,
    )


def _normalize_assignment_device(device: dict) -> DeviceInfo | None:
    device_id = _first_text(device, ("device_id", "id", "printer_id"))
    if not device_id:
        return None
    model = _first_text(device, ("model", "product_name", "type"))
    if model not in SUPPORTED_PRINTER_GROUPS:
        return None
    name = _first_text(device, ("name", "display_name")) or device_id
    status = _first_text(device, ("status", "state", "availability"))
    return DeviceInfo(
        id=device_id,
        name=name,
        model=model,
        status=status,
        is_virtual=_is_virtual_device(device),
    )


def _list_setup_center_printers(settings) -> PreFormPrinterListResponse:
    probe = PreFormSetupService(settings)._probe_server()
    if not probe.get("healthy"):
        return PreFormPrinterListResponse(
            printers=[],
            available=False,
            message=probe.get("message") or "PreFormServer is not ready.",
        )

    client = PreFormClient(settings.preform_server_url)
    try:
        devices = _normalize_device_list(client.list_devices())
    except Exception as exc:
        return PreFormPrinterListResponse(
            printers=[],
            available=False,
            message=str(exc),
        )
    finally:
        client.close()

    printers = [
        _normalize_printer(device, settings=settings)
        for device in devices
        if _is_setup_center_printer(device)
    ]
    return PreFormPrinterListResponse(
        printers=printers,
        available=True,
        message=None,
    )


def _list_assignment_devices(settings) -> PreFormDeviceListResponse:
    probe = PreFormSetupService(settings)._probe_server()
    if not probe.get("healthy"):
        return PreFormDeviceListResponse(
            devices=[],
            available=False,
            message=probe.get("message") or "PreFormServer is not ready.",
        )

    client = PreFormClient(settings.preform_server_url)
    try:
        raw_devices = _normalize_device_list(client.list_devices())
    except Exception as exc:
        return PreFormDeviceListResponse(
            devices=[],
            available=False,
            message=str(exc),
        )
    finally:
        client.close()

    devices = [
        device_info
        for device in raw_devices
        if (device_info := _normalize_assignment_device(device)) is not None
    ]
    return PreFormDeviceListResponse(
        devices=devices,
        available=True,
        message=None,
    )


@router.get("/status", response_model=PreFormSetupStatus)
async def status(request: Request) -> PreFormSetupStatus:
    return await run_in_threadpool(get_preform_setup_status, request.app.state.settings)


@router.get("/dispatch-mode", response_model=DispatchModeStatus)
async def get_dispatch_mode(request: Request) -> DispatchModeStatus:
    return _dispatch_mode_response(request)


@router.patch("/dispatch-mode", response_model=DispatchModeStatus)
async def update_dispatch_mode(
    request: Request,
    payload: UpdateDispatchModeRequest,
) -> DispatchModeStatus:
    request.app.state.settings = replace(
        request.app.state.settings,
        print_dispatch_mode=payload.mode,
    )
    return _dispatch_mode_response(request)


@router.get("/printers", response_model=PreFormPrinterListResponse)
async def get_printers(request: Request) -> PreFormPrinterListResponse:
    return await run_in_threadpool(_list_setup_center_printers, request.app.state.settings)


@router.get("/devices", response_model=PreFormDeviceListResponse)
async def get_devices(request: Request) -> PreFormDeviceListResponse:
    return await run_in_threadpool(_list_assignment_devices, request.app.state.settings)


@router.post("/install-from-zip", response_model=PreFormSetupActionResponse)
async def install_from_zip(
    request: Request,
    package: UploadFile = File(...),
) -> PreFormSetupActionResponse:
    settings = request.app.state.settings
    temp_path = await _save_upload(settings, package)
    try:
        status = _manager(request).install_from_zip(temp_path)
    except PreFormSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
    return _action_response(status, "PreFormServer installed and verified.")


@router.post("/replace-from-zip", response_model=PreFormSetupActionResponse)
async def replace_from_zip(
    request: Request,
    package: UploadFile = File(...),
) -> PreFormSetupActionResponse:
    settings = request.app.state.settings
    temp_path = await _save_upload(settings, package)
    try:
        status = _manager(request).replace_from_zip(temp_path)
    except PreFormSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
    return _action_response(status, "PreFormServer replaced and re-verified.")


@router.post("/start", response_model=PreFormSetupActionResponse)
async def start(request: Request) -> PreFormSetupActionResponse:
    try:
        status = _manager(request).start()
    except PreFormSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _action_response(status, "PreFormServer start requested.")


@router.post("/stop", response_model=PreFormSetupActionResponse)
async def stop(request: Request) -> PreFormSetupActionResponse:
    try:
        status = _manager(request).stop(ignore_missing=False)
    except PreFormSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _action_response(status, "PreFormServer stop requested.")


@router.post("/restart", response_model=PreFormSetupActionResponse)
async def restart(request: Request) -> PreFormSetupActionResponse:
    try:
        status = _manager(request).restart()
    except PreFormSetupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _action_response(status, "PreFormServer restart requested.")


@router.post("/recheck", response_model=PreFormSetupActionResponse)
async def recheck(request: Request) -> PreFormSetupActionResponse:
    status = _manager(request).recheck()
    return _action_response(status, "PreFormServer readiness refreshed.")
