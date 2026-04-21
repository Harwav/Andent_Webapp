from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..schemas import PreFormSetupActionResponse, PreFormSetupStatus
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


@router.get("/status", response_model=PreFormSetupStatus)
async def status(request: Request) -> PreFormSetupStatus:
    return get_preform_setup_status(request.app.state.settings)


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
