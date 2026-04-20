from __future__ import annotations

import shutil
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from ..database import (
    allow_duplicate_rows,
    bulk_delete_upload_rows,
    bulk_update_upload_rows,
    delete_upload_row,
    find_duplicate_hashes,
    get_stored_file_path,
    get_thumbnail_svg,
    get_upload_row_by_id,
    list_queue_rows,
    persist_upload_session,
    send_rows_to_print,
    update_upload_row,
)
from ..schemas import (
    BatchPlanPreviewResponse,
    BulkDeleteRowsResponse,
    BulkUpdateClassificationRowsRequest,
    ClassificationRow,
    PlanPreviewRow,
    QueueSnapshotResponse,
    RowIdsRequest,
    UpdateClassificationRowRequest,
    UploadClassificationResponse,
)
from ..services.planning_preview import build_batch_preview, build_row_preview
from ..services.classification import (
    classify_saved_upload,
    dedupe_filename,
    derive_status,
    file_content_hash,
    sanitize_filename,
    serialize_row_for_storage,
)


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/classify", response_model=UploadClassificationResponse)
async def classify_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
) -> UploadClassificationResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one STL file.")

    settings = request.app.state.settings
    session_id = uuid4().hex
    session_dir = settings.uploads_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    persisted_rows = []
    seen_names: dict[str, int] = {}
    uploaded_hashes: set[str] = set()

    try:
        pending_uploads: list[tuple[UploadFile, str, str, bytes]] = []
        for upload in files:
            original_filename = sanitize_filename(upload.filename)
            if not original_filename.lower().endswith(".stl"):
                await upload.close()
                continue
            payload = await upload.read()
            content_hash = file_content_hash(payload)
            pending_uploads.append((upload, original_filename, content_hash, payload))

        if not pending_uploads:
            raise HTTPException(status_code=400, detail="Upload at least one STL file.")

        duplicate_hashes = find_duplicate_hashes(settings, [content_hash for _, _, content_hash, _ in pending_uploads])

        for upload, original_filename, content_hash, payload in pending_uploads:
            stored_filename = dedupe_filename(original_filename, seen_names)
            stored_path = session_dir / stored_filename
            stored_path.write_bytes(payload)

            try:
                row = classify_saved_upload(stored_path, original_filename)
                if content_hash in duplicate_hashes or content_hash in uploaded_hashes:
                    row.status = "Duplicate"
                else:
                    row.status = derive_status(row.confidence, row.model_type, row.preset)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{original_filename}: {exc}",
                ) from exc
            finally:
                await upload.close()

            rows.append(row)
            persisted_rows.append(serialize_row_for_storage(row, stored_path, content_hash))
            uploaded_hashes.add(content_hash)

        stored_rows = persist_upload_session(settings, session_id, persisted_rows)
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    return UploadClassificationResponse(
        file_count=len(stored_rows),
        rows=stored_rows,
    )


@router.get("/queue", response_model=QueueSnapshotResponse)
async def get_queue(request: Request) -> QueueSnapshotResponse:
    settings = request.app.state.settings
    active_rows, processed_rows = list_queue_rows(settings)
    return QueueSnapshotResponse(active_rows=active_rows, processed_rows=processed_rows)


@router.patch("/rows/{row_id}", response_model=ClassificationRow)
async def patch_upload_row(
    request: Request,
    row_id: int,
    payload: UpdateClassificationRowRequest,
) -> ClassificationRow:
    settings = request.app.state.settings
    try:
        updated_row = update_upload_row(
            settings,
            row_id,
            payload.model_type,
            payload.preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated_row is None:
        raise HTTPException(status_code=404, detail="Upload row not found.")
    return updated_row


@router.post("/rows/bulk-update", response_model=list[ClassificationRow])
async def bulk_patch_upload_rows(
    request: Request,
    payload: BulkUpdateClassificationRowsRequest,
) -> list[ClassificationRow]:
    if payload.model_type is None and payload.preset is None:
        raise HTTPException(status_code=400, detail="Provide a model type or preset to update.")

    settings = request.app.state.settings
    try:
        return bulk_update_upload_rows(
            settings,
            payload.row_ids,
            payload.model_type,
            payload.preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/rows/allow-duplicate", response_model=list[ClassificationRow])
async def bulk_allow_duplicate(request: Request, payload: RowIdsRequest) -> list[ClassificationRow]:
    settings = request.app.state.settings
    return allow_duplicate_rows(settings, payload.row_ids)


@router.post("/rows/send-to-print", response_model=list[ClassificationRow])
async def bulk_send_to_print(request: Request, payload: RowIdsRequest) -> list[ClassificationRow]:
    settings = request.app.state.settings
    return send_rows_to_print(settings, payload.row_ids)


@router.post("/rows/bulk-delete", response_model=BulkDeleteRowsResponse)
async def bulk_remove_upload_rows(request: Request, payload: RowIdsRequest) -> BulkDeleteRowsResponse:
    settings = request.app.state.settings
    try:
        deleted_ids = bulk_delete_upload_rows(settings, payload.row_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BulkDeleteRowsResponse(deleted_row_ids=deleted_ids)


@router.delete("/rows/{row_id}")
async def remove_upload_row(request: Request, row_id: int) -> dict[str, bool]:
    settings = request.app.state.settings
    try:
        deleted = delete_upload_row(settings, row_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Upload row not found.")
    return {"deleted": True}


@router.get("/rows/{row_id}/file", include_in_schema=False)
async def get_row_file(request: Request, row_id: int) -> FileResponse:
    settings = request.app.state.settings
    stored_path = get_stored_file_path(settings, row_id)
    if stored_path is None or not stored_path.exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")
    return FileResponse(stored_path, media_type="model/stl", filename=stored_path.name)


@router.get("/rows/{row_id}/thumbnail.svg", include_in_schema=False)
async def get_row_thumbnail(request: Request, row_id: int) -> Response:
    settings = request.app.state.settings
    svg = get_thumbnail_svg(settings, row_id)
    if svg is None:
        raise HTTPException(status_code=404, detail="Preview not found.")
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/rows/{row_id}/plan-preview", response_model=PlanPreviewRow)
async def get_row_plan_preview(request: Request, row_id: int) -> PlanPreviewRow:
    settings = request.app.state.settings
    row = get_upload_row_by_id(settings, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload row not found.")
    return build_row_preview(row)


@router.post("/rows/batch-plan-preview", response_model=BatchPlanPreviewResponse)
async def batch_plan_preview(request: Request, payload: RowIdsRequest) -> BatchPlanPreviewResponse:
    settings = request.app.state.settings
    rows = [get_upload_row_by_id(settings, rid) for rid in payload.row_ids]
    rows = [r for r in rows if r is not None]
    return build_batch_preview(rows)
