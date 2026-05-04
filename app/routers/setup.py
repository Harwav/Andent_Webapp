from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .. import state as runtime_state
from ..database import load_preform_setup_state

router = APIRouter()


class CompletePayload(BaseModel):
    allow_lan: bool = True


@router.get("/setup", include_in_schema=False)
async def setup_page(request: Request):
    settings = request.app.state.settings
    state = load_preform_setup_state(settings)
    if state.get("readiness") == "ready" and runtime_state.WIZARD_COMPLETED:
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(settings.static_dir / "setup.html")


@router.get("/api/setup/lan-ip")
async def lan_ip(request: Request) -> dict:
    return {
        "lan_ip": getattr(request.app.state, "lan_ip", runtime_state.LAN_IP),
        "port": request.app.state.settings.server_port,
    }


@router.post("/api/setup/complete")
async def complete(payload: CompletePayload | None = None) -> dict:
    runtime_state.WIZARD_COMPLETED = True
    runtime_state.LAN_BIND_ALLOWED = bool(payload.allow_lan) if payload else True
    return {
        "ok": True,
        "wizard_completed": True,
        "lan_allowed": runtime_state.LAN_BIND_ALLOWED,
    }
