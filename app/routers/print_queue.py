"""Print Queue Router - API endpoints for print job management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ..database import get_print_job_by_id
from ..schemas import PrintJob, PrintJobListResponse
from ..services.print_queue_service import get_print_job_screenshot as fetch_print_job_screenshot
from ..services.print_queue_service import release_held_print_job
from ..services.print_queue_service import sync_print_jobs


router = APIRouter(prefix="/api/print-queue", tags=["print-queue"])


@router.get("/jobs", response_model=PrintJobListResponse)
async def list_print_jobs(request: Request) -> PrintJobListResponse:
    settings = request.app.state.settings
    jobs = sync_print_jobs(settings)
    return PrintJobListResponse(jobs=jobs, total_count=len(jobs))


@router.get("/jobs/{job_id}/screenshot")
async def get_job_screenshot(request: Request, job_id: str) -> Response:
    settings = request.app.state.settings

    try:
        job_id_int = int(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    if get_print_job_by_id(settings, job_id_int) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        screenshot_bytes = fetch_print_job_screenshot(settings, job_id_int)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(content=screenshot_bytes, media_type="image/png")


@router.post("/jobs/{job_id}/release-now", response_model=PrintJob)
async def release_job_now(request: Request, job_id: str) -> PrintJob:
    settings = request.app.state.settings

    try:
        job_id_int = int(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    try:
        return release_held_print_job(settings, job_id_int, released_by_operator=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
